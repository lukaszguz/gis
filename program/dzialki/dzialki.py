#!/usr/bin/env python3
"""Pobieranie i eksport granic działek. Python 3.10+. Zobacz INSTRUKCJA.md."""
import argparse
import csv
import json
import math
import re
import sys
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pyproj import CRS, Transformer
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.geometry.polygon import orient
from shapely.ops import transform

LUBLIN = 'https://gis.lublin.eu/iip/ows'
TARGET = CRS.from_epsg(2179)
SESSION = requests.Session()
SESSION.mount('https://', HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1,
    status_forcelist=[429, 502, 503, 504], respect_retry_after_header=True)))

@dataclass
class Parcel:
    id: str
    geom: object  # wewnętrznie zawsze easting, northing (GIS)


def local(tag):
    return tag.rsplit('}', 1)[-1]


def get(url, params):
    r = SESSION.get(url, params=params, timeout=(15, 90))
    r.raise_for_status()
    return r.content


def validate(geom):
    if geom.geom_type not in ('Polygon', 'MultiPolygon') or geom.is_empty:
        raise ValueError('Odpowiedź nie zawiera powierzchni działki.')
    if not geom.is_valid:
        raise ValueError('Niepoprawna topologia granicy; geometria nie będzie automatycznie zmieniana.')
    if not all(math.isfinite(v) for v in geom.bounds):
        raise ValueError('Niefinitywne współrzędne geometrii.')
    return geom


def from_uldk(parcel_id):
    data = get('https://uldk.gugik.gov.pl/', dict(request='GetParcelById',
        id=parcel_id, result='geom_wkt,id', srid=2179)).decode('utf-8-sig').strip()
    lines = data.splitlines()
    if not lines or lines[0].strip() != '0':
        raise ValueError(f'ULDK, {parcel_id}: {data[:400]}')
    results = []
    for line in lines[1:]:
        if not line.strip():
            continue
        geom_text, found_id = line.strip().rsplit('|', 1)
        geom_text = re.sub(r'^SRID=2179;', '', geom_text, flags=re.I)
        if found_id != parcel_id:
            raise ValueError(f'ULDK zwrócił inne ID: {found_id!r} zamiast {parcel_id!r}.')
        results.append(Parcel(found_id, validate(wkt.loads(geom_text))))
    if len(results) != 1:
        raise ValueError(f'ULDK: oczekiwano jednej działki {parcel_id}, otrzymano {len(results)}.')
    return results[0]


def parse_gml(data, source_crs=None, axis='auto', id_field='ID_DZIALKI', layer=None):
    root = ET.fromstring(data)
    if any(local(e.tag) in ('Exception', 'ServiceException') for e in root.iter()):
        raise ValueError('Błąd WFS: ' + ' '.join(root.itertext())[:700])
    candidates = []
    for e in root.iter():
        if local(e.tag) in ('featureMember', 'member'):
            candidates.extend(list(e))
        elif local(e.tag) == 'featureMembers':
            candidates.extend(list(e))
    result = []
    for feature in candidates:
        if layer and local(feature.tag) != layer.split(':')[-1]:
            continue
        values = {local(e.tag): (e.text or '').strip() for e in feature}
        parcel_id = values.get(id_field) or values.get('idDzialki')
        if not parcel_id:  # Pomija budynki, punkty i dane osobowe.
            continue
        parents = {c: p for p in feature.iter() for c in p}
        polygons = []
        for poly in feature.iter():
            if local(poly.tag) not in ('Polygon', 'PolygonPatch'):
                continue
            ancestor = poly
            srs = source_crs
            while srs is None:
                srs = ancestor.get('srsName')
                if srs or ancestor not in parents:
                    break
                ancestor = parents[ancestor]
            if not srs:
                raise ValueError(f'{parcel_id}: brak CRS. Podaj --source-crs EPSG:2179.')
            crs = CRS.from_user_input(srs)
            swap = axis == 'ne' or (axis == 'auto' and crs.axis_info[0].direction == 'north')
            projector = Transformer.from_crs(crs, TARGET, always_xy=True)
            rings = []
            for boundary in poly:
                kind = local(boundary.tag)
                if kind not in ('exterior', 'interior', 'outerBoundaryIs', 'innerBoundaryIs'):
                    continue
                coords = []
                for element in boundary.iter():
                    name = local(element.tag)
                    if name in ('Arc', 'ArcString', 'Circle'):
                        raise ValueError('Łuki GML nie są obsługiwane; nie będą zastępowane odcinkami.')
                    if name in ('posList', 'pos'):
                        a = element
                        dim = None
                        while True:
                            dim = a.get('srsDimension') or a.get('dimension')
                            if dim or a not in parents:
                                break
                            a = parents[a]
                        dim = int(dim or 2)
                        numbers = [float(v) for v in (element.text or '').split()]
                        if dim not in (2, 3) or len(numbers) % dim:
                            raise ValueError(f'{parcel_id}: nieprawidłowy posList.')
                        coords.extend((numbers[i], numbers[i+1]) for i in range(0, len(numbers), dim))
                    elif name == 'coordinates':
                        if element.get('decimal', '.') != '.' or element.get('cs', ',') != ',' or element.get('ts', ' ') != ' ':
                            raise ValueError('Niestandardowe separatory GML2 nie są obsługiwane.')
                        coords.extend(tuple(map(float, v.split(',')[:2])) for v in (element.text or '').split())
                if len(coords) < 4 or coords[0] != coords[-1]:
                    raise ValueError(f'{parcel_id}: niepełny lub nieobsługiwany pierścień GML (np. xlink).')
                if swap:
                    coords = [(b, a) for a, b in coords]
                coords = [projector.transform(a, b) for a, b in coords]
                rings.append((kind in ('exterior', 'outerBoundaryIs'), coords))
            shells = [c for exterior, c in rings if exterior]
            if len(shells) != 1:
                raise ValueError(f'{parcel_id}: brak jednoznacznej granicy zewnętrznej.')
            polygons.append(Polygon(shells[0], [c for exterior, c in rings if not exterior]))
        if not polygons:
            raise ValueError(f'{parcel_id}: brak obsługiwanej geometrii Polygon/PolygonPatch.')
        result.append(Parcel(parcel_id, validate(polygons[0] if len(polygons) == 1 else MultiPolygon(polygons))))
    return result


def rectangle(values):
    x1, y1, x2, y2 = values  # geodezyjne X=N, Y=E
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Współrzędne muszą być liczbami skończonymi.')
    if x1 == x2 or y1 == y2:
        raise ValueError('Prostokąt ma zerową szerokość lub wysokość.')
    return min(y1,y2), min(x1,x2), max(y1,y2), max(x1,x2)


def from_bbox(bounds, url, layer, id_field, limit=100, max_depth=12):
    """WFS 1.1.0. Dzieli pełne odpowiedzi zamiast zakładać, że serwer nie uciął danych."""
    def fetch(b, depth):
        west, south, east, north = b
        data = get(url, dict(SERVICE='WFS', VERSION='1.1.0', REQUEST='GetFeature',
            TYPENAME=layer, SRSNAME='urn:ogc:def:crs:EPSG::2179',
            BBOX=f'{south},{west},{north},{east},urn:ogc:def:crs:EPSG::2179', MAXFEATURES=limit))
        root = ET.fromstring(data)
        features = sum(1 for e in root.iter() if local(e.tag) in ('featureMember','member'))
        features += sum(len(e) for e in root.iter() if local(e.tag) == 'featureMembers')
        reported = root.get('numberOfFeatures') or root.get('numberReturned')
        if reported and reported.isdigit():
            features = max(features, int(reported))
        truncated = any('truncat' in str(v).lower() and str(v).lower() not in ('false','0')
                        for e in root.iter() for k,v in e.attrib.items() if local(k) == 'reason')
        if features >= limit or truncated:
            if depth >= max_depth:
                raise ValueError('Osiągnięto limit WFS mimo podziału obszaru. Zmniejsz prostokąt; nie zapisano niepełnego wyniku.')
            if east-west >= north-south:
                mid = (west+east)/2
                a,b = (west,south,mid,north),(mid,south,east,north)
            else:
                mid = (south+north)/2
                a,b = (west,south,east,mid),(west,mid,east,north)
            return fetch(a,depth+1)+fetch(b,depth+1)
        return parse_gml(data, id_field=id_field, layer=layer)
    area = box(*bounds)
    return unique(p for p in fetch(bounds,0) if p.geom.intersects(area))


def unique(parcels):
    found = {}
    for p in parcels:
        if p.id in found and not p.geom.equals(found[p.id].geom):
            raise ValueError(f'Sprzeczne geometrie dla ID {p.id}.')
        found[p.id] = p
    return [found[k] for k in sorted(found)]


def parts(geom):
    return [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)


def export(parcels, directory, formats=('txt','dxf','shp'), txt_mode='group', labels=False):
    import ezdxf
    import shapefile
    parcels = unique(parcels)
    if not parcels:
        raise ValueError('Nie znaleziono działek; nie utworzono pustych plików.')
    directory = Path(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    # Dopiero kompletny wynik zastępuje pliki docelowe.
    with tempfile.TemporaryDirectory(dir=directory.parent) as tmp:
        out = Path(tmp)
        if 'txt' in formats:
            with (out/'dzialki.txt').open('w', encoding='utf-8', newline='') as f, (out/'pierscienie.csv').open('w',encoding='utf-8-sig',newline='') as mf:
                mapping = csv.writer(mf,delimiter=';')
                mapping.writerow(['grupa','id_dzialki','czesc','pierscien','typ','pierwszy_wiersz_txt','ostatni_wiersz_txt'])
                line = 0
                for group,p in enumerate(parcels):
                    for part,poly in enumerate(parts(p.geom)):
                        for ring_idx,ring in enumerate([poly.exterior,*poly.interiors]):
                            start = line+1
                            for east,north in ring.coords:
                                f.write(f'{north:.2f} {east:.2f}' + (f' 0.000 {group}' if txt_mode == 'group' else '') + '\r\n')
                                line += 1
                            mapping.writerow([group,p.id,part,ring_idx,'zewnetrzny' if ring_idx==0 else 'wewnetrzny',start,line])
        with (out/'dzialki.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f,delimiter=';'); writer.writerow(['grupa','id_dzialki'])
            writer.writerows((i,p.id) for i,p in enumerate(parcels))
        if 'dxf' in formats:
            doc=ezdxf.new('R2010');doc.units=6
            doc.layers.new('GRANICE');doc.layers.new('NUMERY')
            model=doc.modelspace()
            for group,p in enumerate(parcels):
                for poly in parts(p.geom):
                    for ring in [poly.exterior,*poly.interiors]:
                        model.add_lwpolyline(list(ring.coords)[:-1],close=True,dxfattribs={'layer':'GRANICE','elevation':0})
                if labels:
                    q=p.geom.representative_point()
                    model.add_text(p.id,dxfattribs={'height':2.0,'layer':'NUMERY','insert':(q.x,q.y)})
            doc.saveas(out/'dzialki.dxf')
        if 'shp' in formats:
            with shapefile.Writer(str(out/'dzialki'), shapeType=shapefile.POLYGON, encoding='utf-8') as sf:
                sf.field('GRUPA','N',decimal=0);sf.field('ID_DZIALKI','C',size=120)
                for group,p in enumerate(parcels):
                    rings=[]
                    for poly in parts(p.geom):
                        poly=orient(poly,sign=-1.0)
                        rings.extend([list(poly.exterior.coords),*[list(r.coords) for r in poly.interiors]])
                    sf.poly(rings);sf.record(group,p.id)
            (out/'dzialki.prj').write_text(TARGET.to_wkt(version='WKT1_ESRI'),encoding='utf-8')
            (out/'dzialki.cpg').write_text('UTF-8',encoding='ascii')
        (out/'informacje.json').write_text(json.dumps(dict(crs='EPSG:2179',liczba_dzialek=len(parcels),
            txt_osie='X=northing Y=easting',cad_gis_osie='x=easting y=northing',
            uwaga='TXT: zamknięte pierścienie, indeks działki od 0; części i otwory opisane w pierscienie.csv.'),ensure_ascii=False,indent=2),encoding='utf-8')
        directory.mkdir(parents=True,exist_ok=True)
        for file in out.iterdir():
            shutil.copy2(file,directory/file.name)
    return len(parcels)


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--ids',nargs='+',help='Pełne ID działek (jedno lub wiele).')
    source.add_argument('--ids-file',type=Path,help='Plik UTF-8: po jednym pełnym ID w wierszu.')
    source.add_argument('--bbox',type=float,nargs=4,metavar=('X1','Y1','X2','Y2'),help='Dwa przeciwległe narożniki, geodezyjne X Y, EPSG:2179.')
    source.add_argument('--gml',type=Path,help='Konwersja lokalnego GML, bez internetu.')
    p.add_argument('--wfs-url',default=LUBLIN)
    p.add_argument('--layer',default='ms:dzialki')
    p.add_argument('--id-field',default='ID_DZIALKI')
    p.add_argument('--limit',type=int,default=100,help='MAXFEATURES, nie większy od limitu serwera.')
    p.add_argument('--source-crs',help='Wymusza CRS lokalnego GML, np. EPSG:2179.')
    p.add_argument('--gml-axis',choices=['auto','ne','en'],default='auto')
    p.add_argument('--out',type=Path,default=Path('wynik'))
    p.add_argument('--formats',nargs='+',choices=['txt','dxf','shp'],default=['txt','dxf','shp'])
    p.add_argument('--txt-mode',choices=['group','xy'],default='group')
    p.add_argument('--labels',action='store_true',help='Dodaj ID działek jako tekst w DXF.')
    return p


def run(args):
    if args.gml:
        parcels=parse_gml(args.gml.read_bytes(),args.source_crs,args.gml_axis,args.id_field)
    elif args.bbox:
        if args.limit<2:
            raise ValueError('--limit musi wynosić co najmniej 2.')
        parcels=from_bbox(rectangle(args.bbox),args.wfs_url,args.layer,args.id_field,args.limit)
    else:
        ids=args.ids or [s.strip() for s in args.ids_file.read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.lstrip().startswith('#')]
        parcels=[]
        for parcel_id in dict.fromkeys(ids):
            print('Pobieranie:',parcel_id,flush=True)
            parcels.append(from_uldk(parcel_id))
    count=export(parcels,args.out,args.formats,args.txt_mode,args.labels)
    return f'Zapisano {count} działek w: {args.out.resolve()}'


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import threading
    root=tk.Tk();root.title('Granice działek — TXT / DXF / SHP')
    root.geometry('790x760')
    frame=ttk.Frame(root,padding=16);frame.pack(fill='both',expand=True)
    mode=tk.StringVar(value='ids')
    for title,value in [('Pobierz po ID (ULDK, Polska)','ids'),('Pobierz prostokąt (WFS)','bbox'),('Konwertuj lokalny GML','gml')]:
        ttk.Radiobutton(frame,text=title,variable=mode,value=value).pack(anchor='w')
    ttk.Label(frame,text='ID działek — jedno w wierszu:').pack(anchor='w',pady=(10,0))
    ids=tk.Text(frame,height=4);ids.pack(fill='x')
    fields={}
    def field(key,label,default=''):
        ttk.Label(frame,text=label).pack(anchor='w')
        v=tk.StringVar(value=default);ttk.Entry(frame,textvariable=v).pack(fill='x');fields[key]=v
    field('bbox','Narożniki: X1 Y1 X2 Y2 (2000/8, X=północ, Y=wschód)')
    field('url','Adres WFS (dotyczy prostokąta)',LUBLIN)
    field('layer','Warstwa WFS','ms:dzialki')
    field('id_field','Pole ID w WFS','ID_DZIALKI')
    field('gml','Plik GML')
    def browse_gml():
        f=filedialog.askopenfilename(filetypes=[('GML','*.gml'),('Wszystkie','*')])
        if f: fields['gml'].set(f);mode.set('gml')
    ttk.Button(frame,text='Wybierz GML…',command=browse_gml).pack(anchor='w')
    field('out','Katalog wyniku',str(Path.cwd()/'wynik'))
    status=tk.StringVar(value='Wynik: TXT + DXF + SHP. Internet potrzebny tylko przy pobieraniu.')
    ttk.Label(frame,textvariable=status,wraplength=750).pack(anchor='w',pady=8)
    def start():
        argv=['--out',fields['out'].get()]
        if mode.get()=='ids':argv+=['--ids',*ids.get('1.0','end').split()]
        elif mode.get()=='bbox':argv+=['--bbox',*fields['bbox'].get().split(),'--wfs-url',fields['url'].get(),'--layer',fields['layer'].get(),'--id-field',fields['id_field'].get()]
        else:argv+=['--gml',fields['gml'].get()]
        try:args=parser().parse_args(argv)
        except SystemExit:
            messagebox.showerror('Dane wejściowe','Uzupełnij ID, cztery współrzędne narożników lub ścieżkę GML.');return
        button.config(state='disabled');status.set('Praca w toku…')
        def finished(message,error=False):
            button.config(state='normal');status.set(message)
            (messagebox.showerror if error else messagebox.showinfo)('Wynik',message)
        def worker():
            try:
                result=run(args);root.after(0,lambda:finished(result))
            except Exception as e:
                message=str(e);root.after(0,lambda:finished(message,True))
        threading.Thread(target=worker,daemon=True).start()
    button=ttk.Button(frame,text='Pobierz / konwertuj',command=start);button.pack(anchor='w')
    root.mainloop()

if __name__=='__main__':
    try:
        if len(sys.argv)==1:gui()
        else:print(run(parser().parse_args()))
    except Exception as error:
        print(f'BŁĄD: {error}',file=sys.stderr);sys.exit(1)
