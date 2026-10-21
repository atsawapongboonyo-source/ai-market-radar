"""Explicit issuer snapshot refresh. Review generated file before a feature release.
Only downloads publicly published State Street holdings; never invents tickers.
The immutable known_at timestamp is download time, not historical availability.
"""
import argparse,concurrent.futures,hashlib,io,json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen
from openpyxl import load_workbook
FUNDS=('SPY','XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLB','XLU','XLRE','XLC')
def fetch(fund):
    url='https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-'+fund.lower()+'.xlsx'
    with urlopen(url,timeout=25) as r:raw=r.read(3000001)
    if len(raw)>3000000:raise ValueError('ISSUER_FILE_TOO_LARGE')
    rows=list(load_workbook(io.BytesIO(raw),read_only=True,data_only=True).active.values)
    if rows[1][1]!=fund:raise ValueError('WRONG_FUND')
    asof=datetime.strptime(rows[2][1].removeprefix('As of '),'%d-%b-%Y').date()
    now=datetime.now(timezone.utc)
    if not 0<=(now.date()-asof).days<=7:raise ValueError('STALE_ISSUER_FILE')
    stocks=[{'symbol':r[1],'weight_pct':float(r[4])} for r in rows[5:] if isinstance(r[1],str) and re.fullmatch('[A-Z]{1,5}(?:[.-][A-Z])?',r[1]) and isinstance(r[4],(int,float)) and r[4]>0 and r[7]=='USD']
    if len(stocks)<5:raise ValueError('INCOMPLETE_HOLDINGS')
    return fund,{'as_of':str(asof),'known_at':now.isoformat(),'source':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'kind':'VERIFIED_HOLDINGS','holdings_count':len(stocks),'stocks':sorted(stocks,key=lambda r:-r['weight_pct'])[:5]}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with concurrent.futures.ThreadPoolExecutor(4) as pool:funds=dict(pool.map(fetch,FUNDS))
    version='issuer-'+datetime.now(timezone.utc).strftime('%Y%m%d')+'-'+hashlib.sha256(json.dumps(funds,sort_keys=True).encode()).hexdigest()[:8]
    a.output.write_text(json.dumps({'version':version,'selection':'top5_by_issuer_weight; bounded research subset, not all constituents','funds':funds},indent=2),encoding='utf-8')
    print(json.dumps({'funds':len(funds),'version':version,'output_written':True}))
