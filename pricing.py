"""Persist source prices and manual overrides independently of geometry."""
import json, os, threading
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urlsplit

def lines(model):
    result=[]
    for r in model['materials']:
        s=model['stocks'][r['stock']]
        if r['kind']=='lumber':
            counts={}
            for b in r['bins']: counts[b['length']]=counts.get(b['length'],0)+1
            options=[(f"board:{length:g}",f"{length/12:g} ft board",count) for length,count in sorted(counts.items())]
        elif r['kind'] in ('coverage','product'):
            options=[('unit' if r['kind']=='product' else 'pack',r['unit'],r['quantity'])]
        elif r['kind']=='sheet':
            import math
            options=[('sheet',f"{s['sheet'][0]/12:g} × {s['sheet'][1]/12:g} ft sheet",math.ceil(r['square_ft']/(s['sheet'][0]*s['sheet'][1]/144)))]
        else: options=[('lot','quoted lot',None)]
        for suffix,unit,qty in options:
            result.append(dict(key=f"{r['stock']}:{suffix}",name=r['name'],unit=unit,model_quantity=qty,basis=r['basis'],candidate_url=r['url'],category=r.get('category',s.get('category','Other')),taxable=r.get('taxable',True)))
    return result

class PriceStore:
    def __init__(self,path): self.path=Path(path);self.lock=threading.Lock()
    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {'schema_version':1,'currency':'USD','prices':{}}
    def update(self,payload,model):
        key=payload.get('key');line=next((r for r in lines(model) if r['key']==key),None)
        if not line: raise ValueError('Material or stock length no longer exists.')
        with self.lock:
            data=self.read();entry=data['prices'].setdefault(key,{})
            if payload.get('action')=='clear_manual': entry.pop('manual',None)
            else:
                kind=payload.get('kind','manual')
                if kind not in ('manual','source','estimate'): raise ValueError('Invalid price kind')
                try:
                    price=Decimal(str(payload.get('unit_price')))
                    if not price.is_finite() or price<0 or price>10000000: raise ValueError('Enter a nonnegative price below $10 million.')
                    price=price.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                except InvalidOperation: raise ValueError('Invalid price')
                qty=payload.get('quantity')
                if qty is not None and (type(qty)!=int or not 1<=qty<=1000000): raise ValueError('Quantity must be a positive whole number.')
                source=payload.get('source','').strip();url=payload.get('url','').strip()
                if not source or len(source)>200: raise ValueError('Enter a supplier or source, up to 200 characters.')
                if url and (len(url)>2000 or urlsplit(url).scheme not in ('http','https') or not urlsplit(url).netloc): raise ValueError('Enter a valid source URL.')
                if kind=='source' and not url: raise ValueError('Sourced prices require an evidence URL.')
                observed=payload.get('observed_on','')
                try: date.fromisoformat(observed)
                except (ValueError,TypeError): raise ValueError('Enter a quote date.')
                note=payload.get('note','')
                if not isinstance(note,str) or len(note)>1000: raise ValueError('Note must be at most 1000 characters.')
                entry[kind]=dict(unit_price=str(price),quantity=qty,source=source,url=url,observed_on=observed,note=note,updated_at=datetime.now(timezone.utc).isoformat(),unit=line['unit'])
            self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');os.replace(temp,self.path)
        return self.estimate(model)
    def estimate(self,model):
        data=self.read();rows=lines(model);total=Decimal(0);priced=0
        for row in rows:
            entry=data['prices'].get(row['key'],{});quote_kind=next((kind for kind in ('manual','source','estimate') if entry.get(kind)),None);quote=entry.get(quote_kind) if quote_kind else None
            row.update(quote=quote,quote_kind=quote_kind,has_manual=bool(entry.get('manual')),sourced_quote=entry.get('source'))
            qty=quote.get('quantity') if quote else None
            if qty is None:qty=row['model_quantity']
            row['quantity']=qty;row['total']=None
            if quote and qty is not None:
                cost=(Decimal(quote['unit_price'])*qty).quantize(Decimal('.01'));row['total']=str(cost);total+=cost;priced+=1
        result=dict(currency='USD',rows=rows,subtotal=str(total),priced_lines=priced,unpriced_lines=len(rows)-priced,revision=model['revision'])
        groups={}
        for row in rows:
            groups[row['category']]=groups.get(row['category'],Decimal(0))+Decimal(row['total'] or '0')
        result['categories']={k:str(v) for k,v in groups.items()}
        result['price_kinds']={kind:dict(lines=sum(r['quote_kind']==kind for r in rows),subtotal=str(sum((Decimal(r['total'] or '0') for r in rows if r['quote_kind']==kind),Decimal(0)))) for kind in ('source','manual','estimate')}
        config=model.get('budget')
        if config:
            taxable=sum((Decimal(r['total'] or '0') for r in rows if r['taxable']),Decimal(0))
            tax=(taxable*Decimal(config['sales_tax_rate'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            reserve=((total+tax)*Decimal(config['contingency_rate'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            grand=total+tax+reserve
            result['budget']=dict(**config,taxable_subtotal=str(taxable),sales_tax=str(tax),contingency=str(reserve),grand_total=str(grand),over_target=str(max(Decimal(0),grand-Decimal(config['target']))),complete=priced==len(rows))
        return result
