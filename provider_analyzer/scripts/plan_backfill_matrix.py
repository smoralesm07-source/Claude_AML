#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os
from datetime import datetime,timezone
from intelligence_fusion.public_integrity_calendar import monthly_window
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start-year',type=int,default=2024);ap.add_argument('--start-month',type=int,default=1);ap.add_argument('--end-year',type=int);ap.add_argument('--end-month',type=int);ap.add_argument('--github-output',action='store_true');args=ap.parse_args()
    if (args.end_year is None)!=(args.end_month is None):raise SystemExit('end-year and end-month must be provided together')
    if args.end_year is None:
        w=monthly_window(now=datetime.now(timezone.utc),months=1,route_months=1);ey,em=w['year'],w['month']
    else:ey,em=args.end_year,args.end_month
    start=args.start_year*12+(args.start_month-1);end=ey*12+(em-1)
    if start>end:raise SystemExit('start is after end')
    include=[]
    for serial in range(start,end+1):
        y,m=serial//12,serial%12+1;include.append({'year':y,'month':m,'period':f'{y:04d}-{m:02d}'})
    matrix={'include':include};payload={'matrix':matrix,'months':len(include),'start':include[0]['period'],'end':include[-1]['period']}
    if args.github_output:
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as fh:fh.write('matrix='+json.dumps(matrix,separators=(',',':'))+'\n')
    print(json.dumps(payload,ensure_ascii=False))
if __name__=='__main__':main()
