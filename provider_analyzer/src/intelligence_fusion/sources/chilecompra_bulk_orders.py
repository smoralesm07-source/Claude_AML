from __future__ import annotations
import csv, io, re
from pathlib import Path
from typing import Iterable, TextIO
from .common import as_float, clean_rut, norm_text, stable_hash

ALIASES={
    'order_id':('Codigo','Código','CodigoOrdenCompra','Código Orden de Compra','Codigo OC','codigooc'),
    'tender_id':('CodigoLicitacion','CódigoLicitacion','Código Licitación','Codigo Licitacion','idlicitacion'),
    'status':('Estado','EstadoOC','Estado Orden de Compra','estado'),
    'created_at':('FechaCreacion','Fecha Creacion','Fecha de Creación','fechacreacion'),
    'accepted_at':('FechaAceptacion','Fecha Aceptacion','Fecha de Aceptación','fechaaceptacion'),
    'modified_at':('FechaUltimaModificacion','Fecha Última Modificación','FechaUltimaModificacionOC','fechaUltimaModificacion','fechaultimamodificacion'),
    'buyer_name':('OrganismoPublico','NombreOrganismo','Organismo','Nombre Organismo','nombreorganismo'),
    'buyer_rut':('RutUnidadCompra','RUT Unidad Compra','RutUnidad','RUT Unidad','RutOrganismo','RUT Organismo','rutunidad','rutorganismo'),
    'buyer_unit':('UnidadCompra','NombreUnidad','Unidad de Compra','nombreunidad'),
    'buyer_region':('RegionUnidadCompra','Región Unidad Compra','RegionUnidad','Región Unidad','Region Organismo','regionunidad'),
    'buyer_commune':('CiudadUnidadCompra','ComunaUnidadCompra','ComunaUnidad','Comuna Unidad','comunaunidad'),
    'supplier_name':('NombreProveedor','Sucursal','Proveedor','Nombre Proveedor','nombreproveedor'),
    'supplier_rut':('RutSucursal','RUT Sucursal','RutProveedor','RUT Proveedor','rutproveedor','rutsucursal'),
    'currency':('TipoMonedaOC','TipoMoneda','Moneda','tipo moneda','tipomoneda'),
    'net_amount':('TotalNetoOC','Neto','MontoNeto','Monto Neto','neto'),
    'tax_amount':('Impuestos','Iva','IVA','Impuesto','MontoIVA','montoiva'),
    'total_amount':('MontoTotalOC','Total','MontoTotal','Monto Total','total'),
    'total_amount_clp':('MontoTotalOC_PesosChilenos','Monto Total OC Pesos Chilenos','montototalocpesoschilenos'),
    'modality':('Tipo','DescripcionTipoOC','TipoCompra','Modalidad','MecanismoCompra','Mecanismo de Compra','tipocompra'),
    'item_line':('IDItem','Correlativo','Linea','Línea','NumeroLinea','numero linea'),
    'product_code':('codigoProductoONU','CodigoProducto','CódigoProducto','Código Producto','codigoproducto'),
    'product_name':('NombreroductoGenerico','NombreProductoGenerico','NombreProducto','Producto','Nombre Producto','nombreproducto'),
    'description':('EspecificacionComprador','Especificación Comprador','Descripcion','Descripción','descripcion'),
    'quantity':('Cantidad','cantidad'),
    'unit':('UnidadMedida','Unidad de Medida','unidadmedida'),
    'unit_price':('precioNeto','PrecioNeto','PrecioUnitario','Precio Neto','Precio Unitario','precioneto'),
    'line_total':('totalLineaNeto','TotalItem','Total Item','MontoLinea','Monto Línea','totalitem'),
}

class ChileCompraBulkOrdersAdapter:
    producer_id='SOURCE_CHILECOMPRA_BULK_ORDERS'

    @staticmethod
    def _key(s:str)->str:
        return re.sub(r'[^a-z0-9]','',norm_text(s).lower())

    @classmethod
    def resolve_columns(cls,fieldnames:Iterable[str]|None)->dict[str,str]:
        fields=[f for f in (fieldnames or []) if f]
        by_norm={cls._key(f):f for f in fields}
        out={}
        for canonical,aliases in ALIASES.items():
            for alias in aliases:
                hit=by_norm.get(cls._key(alias))
                if hit:
                    out[canonical]=hit;break
        return out

    @staticmethod
    def sniff(text:str)->csv.Dialect:
        try:return csv.Sniffer().sniff(text[:12000],delimiters=';,\t|')
        except csv.Error:
            class Semi(csv.excel): delimiter=';'
            return Semi()

    @classmethod
    def read_rows(cls,fh:TextIO,limit:int|None=None)->tuple[list[dict],dict]:
        text=fh.read();dialect=cls.sniff(text);reader=csv.DictReader(io.StringIO(text),dialect=dialect)
        mapping=cls.resolve_columns(reader.fieldnames);rows=[]
        for i,row in enumerate(reader):
            if limit is not None and i>=limit:break
            rows.append(row)
        return rows,{'delimiter':dialect.delimiter,'columns':list(reader.fieldnames or []),'mapping':mapping}

    @classmethod
    def read_path(cls,path:Path,limit:int|None=None)->tuple[list[dict],dict]:
        for enc in ('utf-8-sig','utf-8','latin-1'):
            try:
                with path.open('r',encoding=enc,newline='') as fh: rows,meta=cls.read_rows(fh,limit=limit)
                meta['encoding']=enc;meta['path']=str(path);return rows,meta
            except UnicodeDecodeError:continue
        raise UnicodeError(f'Cannot decode {path}')

    @staticmethod
    def _get(row:dict,m:dict,key:str):
        col=m.get(key);return row.get(col) if col else None

    @classmethod
    def normalize(cls,rows:list[dict],meta:dict)->list[dict]:
        m=meta.get('mapping') or {};orders={}
        for row in rows:
            oid=str(cls._get(row,m,'order_id') or '').strip()
            if not oid:continue
            if oid not in orders:
                orders[oid]={
                    'source':'MERCADO_PUBLICO_BULK_ORDERS','order_id':oid,'tender_id':cls._get(row,m,'tender_id'),'status':cls._get(row,m,'status'),
                    'created_at':cls._get(row,m,'created_at'),'accepted_at':cls._get(row,m,'accepted_at'),'modified_at':cls._get(row,m,'modified_at'),
                    'buyer':{'rut':clean_rut(cls._get(row,m,'buyer_rut')),'name':cls._get(row,m,'buyer_name'),'unit':cls._get(row,m,'buyer_unit'),'region':cls._get(row,m,'buyer_region'),'commune':cls._get(row,m,'buyer_commune')},
                    'supplier':{'rut':clean_rut(cls._get(row,m,'supplier_rut')),'name':cls._get(row,m,'supplier_name')},
                    'currency':cls._get(row,m,'currency'),'amount_net':as_float(cls._get(row,m,'net_amount')),'amount_tax':as_float(cls._get(row,m,'tax_amount')),'amount_total':as_float(cls._get(row,m,'total_amount')),'amount_total_clp':as_float(cls._get(row,m,'total_amount_clp')),
                    'modality':cls._get(row,m,'modality'),'items':[]}
            item={
                'line':cls._get(row,m,'item_line'),'product_code':cls._get(row,m,'product_code'),'name':cls._get(row,m,'product_name'),'description':cls._get(row,m,'description'),
                'quantity':as_float(cls._get(row,m,'quantity')),'unit':cls._get(row,m,'unit'),'unit_price':as_float(cls._get(row,m,'unit_price')),'line_total':as_float(cls._get(row,m,'line_total'))}
            if any(v not in (None,'') for v in item.values()):orders[oid]['items'].append(item)
        out=[]
        for order in orders.values():
            sid=(order.get('supplier') or {}).get('rut') or norm_text((order.get('supplier') or {}).get('name'))
            bid=(order.get('buyer') or {}).get('rut') or norm_text((order.get('buyer') or {}).get('name'))
            order['pair_key']=f'{sid}::{bid}' if sid and bid else None;order['record_hash']=stable_hash(order);out.append(order)
        return out

    @classmethod
    def coverage(cls,orders:list[dict],meta:dict)->dict:
        items=sum(len(o.get('items') or []) for o in orders);priced=sum(1 for o in orders for i in o.get('items') or [] if i.get('unit_price') not in (None,0))
        with_buyer=sum(1 for o in orders if (o.get('buyer') or {}).get('rut') or (o.get('buyer') or {}).get('name'))
        with_supplier=sum(1 for o in orders if (o.get('supplier') or {}).get('rut') or (o.get('supplier') or {}).get('name'))
        with_product=sum(1 for o in orders for i in o.get('items') or [] if i.get('product_code') or i.get('name'))
        with_clp=sum(1 for o in orders if o.get('amount_total_clp') not in (None,0))
        cols=list(meta.get('columns') or []);n=max(len(orders),1)
        return {'orders':len(orders),'items':items,'priced_items':priced,'price_coverage':round(priced/max(items,1),6),'orders_with_buyer':with_buyer,'buyer_coverage':round(with_buyer/n,6),'orders_with_supplier':with_supplier,'supplier_coverage':round(with_supplier/n,6),'orders_with_clp_amount':with_clp,'clp_amount_coverage':round(with_clp/n,6),'items_with_product':with_product,'product_coverage':round(with_product/max(items,1),6),'resolved_columns':sorted((meta.get('mapping') or {}).keys()),'raw_column_count':len(cols),'raw_columns':cols}
