import csv
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
import shapefile
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely import wkt
import dzialki as d

ROOT=Path(__file__).parent

def test_example_and_axes(tmp_path):
    p=d.Parcel('a',wkt.loads('POLYGON((8397008.8 5680645.43,8397014.3 5680622.09,8397017.19 5680626.11,8397018.41 5680636.17,8397008.8 5680645.43))'))
    d.export([p],tmp_path)
    assert (tmp_path/'dzialki.txt').read_text().splitlines()[0]=='5680645.43 8397008.80 0.000 0'
    sf=shapefile.Reader(str(tmp_path/'dzialki'))
    assert shape(sf.shape(0).__geo_interface__).equals(p.geom)
    doc=ezdxf.readfile(tmp_path/'dzialki.dxf')
    assert not doc.audit().has_errors
    entity=list(doc.modelspace().query('LWPOLYLINE'))[0]
    assert entity.closed
    assert list(entity.get_points('xy'))[0]==(8397008.8,5680645.43)

def test_parts_holes_groups(tmp_path):
    a=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(2,2),(2,4),(4,4),(4,2)]])
    b=Polygon([(20,0),(21,0),(21,1),(20,1)])
    geom=MultiPolygon([a,b])
    d.export([d.Parcel('b',b),d.Parcel('a',geom)],tmp_path)
    sf=shapefile.Reader(str(tmp_path/'dzialki'))
    assert shape(sf.shape(0).__geo_interface__).equals(geom)
    assert sf.record(0)[1]=='a'
    rows=list(csv.DictReader((tmp_path/'pierscienie.csv').open(encoding='utf-8-sig'),delimiter=';'))
    assert len(rows)==4
    assert [r['grupa'] for r in rows]==['0','0','0','1']
    assert rows[1]['typ']=='wewnetrzny'
    doc=ezdxf.readfile(tmp_path/'dzialki.dxf')
    assert len(list(doc.modelspace().query('LWPOLYLINE')))==4


def test_gml_axis_crs_and_filter():
    xml=b'''<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:p="urn:p"><gml:featureMember><p:EGB_DzialkaEwidencyjna><p:idDzialki>a</p:idDzialki><p:geometria><gml:Polygon srsName="EPSG:2179"><gml:exterior><gml:LinearRing><gml:posList>5680000 8390000 5680010 8390000 5680010 8390010 5680000 8390000</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></p:geometria></p:EGB_DzialkaEwidencyjna></gml:featureMember><gml:featureMember><p:Building/></gml:featureMember></gml:FeatureCollection>'''
    a=d.parse_gml(xml)
    assert len(a)==1
    assert a[0].geom.bounds==(8390000,5680000,8390010,5680010)
    xml=xml.replace(b'EPSG:2179',b'EPSG:4326').replace(b'5680000 8390000 5680010 8390000 5680010 8390010 5680000 8390000',b'51.2 22.5 51.201 22.5 51.201 22.501 51.2 22.5')
    a=d.parse_gml(xml)[0]
    assert 8300000<a.geom.bounds[0]<8500000
    assert 5600000<a.geom.bounds[1]<5800000


def test_subdivide_no_clipping(monkeypatch):
    calls=[]
    large=d.Parcel('a',Polygon([(0,0),(10,0),(10,10),(0,10)]))
    def get(url,params):
        calls.append(params)
        return b'<FeatureCollection><member/><member/></FeatureCollection>' if len(calls)==1 else b'<FeatureCollection><member/></FeatureCollection>'
    monkeypatch.setattr(d,'get',get)
    monkeypatch.setattr(d,'parse_gml',lambda *a,**kw:[large])
    result=d.from_bbox((1,1,2,2),'url','layer','id',limit=2)
    assert len(calls)==3
    assert len(result)==1 and result[0].geom.equals(large.geom)
    assert calls[0]['BBOX']=='1,1,2,2,urn:ogc:def:crs:EPSG::2179'


def test_limit_not_silently_saved(monkeypatch):
    monkeypatch.setattr(d,'get',lambda *a,**kw:b'<FeatureCollection><member/><member/></FeatureCollection>')
    with pytest.raises(ValueError,match='limit WFS'):
        d.from_bbox((0,0,1,1),'url','layer','id',2,max_depth=1)


def test_no_partial_export(tmp_path):
    f=tmp_path/'dzialki.txt';f.write_text('stary wynik')
    with pytest.raises(ValueError):d.export([],tmp_path)
    assert f.read_text()=='stary wynik'
    with pytest.raises(ValueError):d.rectangle([1,1,1,2])
    with pytest.raises(ValueError):d.rectangle([float('nan'),1,2,3])


def test_uldk_status_and_id(monkeypatch):
    monkeypatch.setattr(d,'get',lambda *a,**kw:b'-1\nBrak dzialki')
    with pytest.raises(ValueError):d.from_uldk('a')
    monkeypatch.setattr(d,'get',lambda *a,**kw:b'0\nSRID=2179;POLYGON((0 0,1 0,1 1,0 0))|b')
    with pytest.raises(ValueError,match='inne ID'):d.from_uldk('a')


def test_provided_exports_readable():
    for name,count in [('jedna_dzialka',1),('dziesiec_dzialek',10)]:
        folder=ROOT/'przyklady'/name
        sf=shapefile.Reader(str(folder/'dzialki'))
        assert len(sf)==count
        assert all(shape(s.__geo_interface__).is_valid for s in sf.shapes())
        doc=ezdxf.readfile(folder/'dzialki.dxf')
        assert not doc.audit().has_errors
        assert len(list(doc.modelspace().query('LWPOLYLINE')))>=count
