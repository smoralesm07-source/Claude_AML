from __future__ import annotations
import csv, io, re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, TextIO
from .common import as_float, clean_rut, norm_text, stable_hash

ALIASES={
    'tender_id':('CodigoExterno','CódigoExterno','codigoexterno','idlicitacion','licitacion'),
    'title':('Nombre','NombreLicitacion','nombrelicitacion'),
    'status':('Estado','EstadoLicitacion','estado'),
    'modality':('Tipo de Adquisicion','TipoAdquisicion','Tipo','tipo'),
    'buyer_name':('NombreOrganismo','Organismo','nombreorganismo'),
    'buyer_rut':('RutUnidad','RutOrganismo','rutunidad','rutorganismo'),
    'buyer_unit':('NombreUnidad','UnidadCompra','nombreunidad'),
    'published_at':('FechaPublicacion','fechapublicacion'),
    'closed_at':('FechaCierre','fechacierre'),
    'awarded_at':('FechaAdjudicacion','fechaadjudicacion'),
    'supplier_rut':('RutProveedor','RUTProveedor','rutproveedor','RutOferente','rutoferente'),
    'supplier_name':('NombreProveedor','Proveedor','nombreproveedor','NombreOferente','nombreoferente'),
    'item_id':('Correlativo','CodigoProducto','CódigoProducto','codigoproducto','Item','item'),
    'product_code':('CodigoProducto','CódigoProducto','codigoproducto','Codigoitem'),
    'product_name':('NombreProducto','Producto','nombreproducto','Nombre producto genrico','Nombre linea Adquisicion'),
    'description':('Descripcion','Descripción','DescripcionItem','descripcionitem','Descripcion linea Adquisicion'),
    'unit':('UnidadMedida','unidadmedida'),
    'quantity':('Cantidad','CantidadLicitada','cantidad'),
    'offer_unit_price':('MontoUnitarioOferta','PrecioUnitarioOferta','MontoOfertaUnitario','ValorUnitarioOferta','PrecioOferta','Oferta','montounitariooferta','preciounitariooferta'),
    'offer_total':('MontoOferta','MontoTotalOferta','ValorOferta','montooferta','montototaloferta','Valor Total Ofertado'),
    'selected_offer':('Oferta seleccionada','OfertaSeleccionada','ofertaseleccionada'),
    'awarded_supplier_rut':('RutProveedorAdjudicado','RutAdjudicado','rutproveedoradjudicado'),
    'awarded_supplier_name':('NombreProveedorAdjudicado','ProveedorAdjudicado','nombreproveedoradjudicado'),
    'awarded_unit_price':('MontoUnitario','MontoUnitarioAdjudicado','PrecioUnitarioAdjudicado','montounitario'),
    'awarded_quantity':('CantidadAdjudicada','cantidadadjudicada'),
    'awarded_line_total':('MontoLineaAdjudica','MontoLineaAdjudicada','montolineaadjudica'),
}

class ChileCompraBulkOffersAdapter:
    producer_id='SOURCE_CHILECOMPRA_BULK_OFFERS'

    @staticmethod
    def _key(s:str)->str:
        return re.sub(r'[^a-z0-9]','',norm_text(s).lower())

    @staticmethod
    def _truthy(value)->bool:
        v=norm_text(value).strip().lower()
        return v in {'1','si','sí','s','true','verdadero','yes','y','seleccionada','seleccionado','adjudicada','adjudicado'}

    @classmethod
    def resolve_columns(cls, fieldnames:Iterable[str]|None)->dict[str,str]:
        fields=[f for f in (fieldnames or []) if f]
        by_norm={cls._key(f):f for f in fields}
        out={}
        for canonical,aliases in ALIASES.items():
            for a in aliases:
                hit=by_norm.get(cls._key(a))
                if hit:
                    out[canonical]=hit;break
        return out

    @staticmethod
    def sniff(text:str)->csv.Dialect:
        sample=text[:12000]
        try:return csv.Sniffer().sniff(sample,delimiters=';,\t|')
        except csv.Error:
            class Semi(csv.excel): delimiter=';'
            return Semi()

    @classmethod
    def read_rows(cls, fh:TextIO, limit:int|None=None)->tuple[list[dict],dict]:
        text=fh.read()
        dialect=cls.sniff(text)
        reader=csv.DictReader(io.StringIO(text,newline=''),dialect=dialect)
        mapping=cls.resolve_columns(reader.fieldnames)
        rows=[]
        for i,row in enumerate(reader):
            if limit is not None and i>=limit:break
            rows.append(row)
        return rows,{'delimiter':dialect.delimiter,'columns':list(reader.fieldnames or []),'mapping':mapping}

    @classmethod
    def read_path(cls,path:Path,limit:int|None=None)->tuple[list[dict],dict]:
        for enc in ('utf-8-sig','utf-8','latin-1'):
            try:
                with path.open('r',encoding=enc,newline='') as fh:
                    rows,meta=cls.read_rows(fh,limit=limit)
                meta['encoding']=enc;meta['path']=str(path);return rows,meta
            except UnicodeDecodeError:continue
        raise UnicodeError(f'Cannot decode {path}')

    @staticmethod
    def _get(row:dict,m:dict,key:str):
        col=m.get(key);return row.get(col) if col else None

    @classmethod
    def normalize(cls, rows:list[dict], meta:dict)->list[dict]:
        m=meta.get('mapping') or {}; grouped=defaultdict(lambda:{'bids':defaultdict(lambda:{'items':[]}), 'awards':defaultdict(lambda:{'items':[]})})
        base={}
        explicit_award_identity=('awarded_supplier_rut' in m or 'awarded_supplier_name' in m)
        selected_offer_available='selected_offer' in m
        for row in rows:
            tid=str(cls._get(row,m,'tender_id') or '').strip()
            if not tid:continue
            if tid not in base:
                base[tid]={'source':'MERCADO_PUBLICO_BULK','tender_id':tid,'title':cls._get(row,m,'title'),'status':cls._get(row,m,'status'),'type':cls._get(row,m,'modality'),'published_at':cls._get(row,m,'published_at'),'closed_at':cls._get(row,m,'closed_at'),'awarded_at':cls._get(row,m,'awarded_at'),'buyer':{'id':clean_rut(cls._get(row,m,'buyer_rut')),'name':cls._get(row,m,'buyer_name'),'unit':cls._get(row,m,'buyer_unit')}}
            sid=clean_rut(cls._get(row,m,'supplier_rut')) or norm_text(cls._get(row,m,'supplier_name'))
            sname=cls._get(row,m,'supplier_name')
            iid=str(cls._get(row,m,'item_id') or cls._get(row,m,'product_code') or '').strip()
            item={'item_id':iid,'product_code':cls._get(row,m,'product_code'),'description':cls._get(row,m,'product_name') or cls._get(row,m,'description'),'quantity':as_float(cls._get(row,m,'quantity')),'unit':cls._get(row,m,'unit'),'unit_price':as_float(cls._get(row,m,'offer_unit_price'))}
            if sid:
                bid=grouped[tid]['bids'][sid];bid['supplier_id']=sid;bid['supplier_name']=sname;bid['value']=as_float(cls._get(row,m,'offer_total'))
                if iid or item['unit_price'] is not None:bid['items'].append(item)
            selected=selected_offer_available and cls._truthy(cls._get(row,m,'selected_offer'))
            if explicit_award_identity or selected:
                arut=(clean_rut(cls._get(row,m,'awarded_supplier_rut')) or norm_text(cls._get(row,m,'awarded_supplier_name'))) if explicit_award_identity else sid
                aname=cls._get(row,m,'awarded_supplier_name') if explicit_award_identity else sname
                aprice=as_float(cls._get(row,m,'awarded_unit_price'))
                if aprice is None and selected: aprice=item['unit_price']
                aqty=as_float(cls._get(row,m,'awarded_quantity'))
                line_total=as_float(cls._get(row,m,'awarded_line_total'))
                if arut and (aprice is not None or aqty is not None or line_total is not None):
                    aw=grouped[tid]['awards'][arut];aw['award_id']=f'{tid}:{arut}';aw['status']='active';aw['suppliers']=[{'id':arut,'name':aname}];aw['items'].append({'item_id':iid,'product_code':cls._get(row,m,'product_code'),'quantity':aqty,'unit_price':aprice,'line_total':line_total,'evidence':'selected_offer' if selected else 'explicit_awarded_supplier'})
        out=[]
        for tid,b in base.items():
            t={**b,'bids':list(grouped[tid]['bids'].values()),'awards':list(grouped[tid]['awards'].values())}
            t['record_hash']=stable_hash(t);out.append(t)
        return out

    @classmethod
    def coverage(cls,tenders:list[dict],meta:dict)->dict:
        bids=sum(len(t.get('bids') or []) for t in tenders)
        bid_items=sum(len(b.get('items') or []) for t in tenders for b in t.get('bids') or [])
        priced=sum(1 for t in tenders for b in t.get('bids') or [] for i in b.get('items') or [] if i.get('unit_price') not in (None,0))
        awards=sum(len(t.get('awards') or []) for t in tenders)
        cols=list(meta.get('columns') or [])
        return {'tenders':len(tenders),'bids':bids,'bid_items':bid_items,'priced_bid_items':priced,'awards':awards,'price_coverage':round(priced/max(bid_items,1),6),'resolved_columns':sorted((meta.get('mapping') or {}).keys()),'raw_column_count':len(cols),'raw_columns':cols}
