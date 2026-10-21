"""Staging-only extension: no provider credentials or network market downloads."""
from datetime import datetime,timezone
import json
from pathlib import Path
from flask import Blueprint,jsonify,request
from rotation_public_protocol import PublicDataError
from rotation_store import StoreUnavailable
from rotation_stock_protocol import parse_stock,verify_stock,MAX_STOCK_BODY,STOCK_PATH

def register_stock(app,store,keys,universe,clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc));bp=Blueprint('rotation_stocks',__name__)
    def current():
        try:
            raw=store.latest()
            if raw is None:return {'status':'BLOCKED','reason':'AWAITING_STOCK_COLLECTOR','stocks':[]}
            return {'status':'RESEARCH_ONLY',**parse_stock(raw,clock(),universe)}
        except PublicDataError as e:return {'status':'BLOCKED','reason':str(e),'stocks':[]}
        except StoreUnavailable:return {'status':'BLOCKED','reason':'STORE_UNAVAILABLE','stocks':[]}
        except (ValueError,KeyError,TypeError):return {'status':'BLOCKED','reason':'INVALID_STOCK_SCHEMA','stocks':[]}
    @bp.get('/api/rotation/stocks')
    def read():return jsonify(current())
    @bp.post(STOCK_PATH)
    def ingest():
        def err(code,status):return jsonify(ok=False,error_code=code),status
        if request.headers.get('X-Forwarded-Proto')!='https' and not request.is_secure:return err('HTTPS_REQUIRED',400)
        if request.content_length is None:return err('CONTENT_LENGTH_REQUIRED',411)
        if request.content_length>MAX_STOCK_BODY:return err('PAYLOAD_TOO_LARGE',413)
        if request.mimetype!='application/json':return err('JSON_REQUIRED',415)
        raw=request.stream.read(MAX_STOCK_BODY+1);now=clock()
        try:
            kid,nonce=verify_stock(raw,request.headers,keys,now);v=parse_stock(raw,now,universe)
            code,http=store.publish(raw,v,kid,nonce,now,signed_timestamp=int(request.headers['X-Rotation-Timestamp']))
            return jsonify({'ok':True,'status':code}) if http==200 else err(code,http)
        except PublicDataError as e:return err(str(e),401 if str(e)=='INVALID_SIGNATURE' else 422)
        except StoreUnavailable:return err('STORE_UNAVAILABLE',503)
    @bp.after_request
    def safe(r):
        r.headers['Content-Security-Policy']="default-src 'none'; frame-ancestors 'none'"
        r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff'
        return r
    app.register_blueprint(bp)
    labels={'SECTOR_NOT_LEADING':'กลุ่มยังไม่นำตลาดทั้งสองช่วง','RELATIVE_STRENGTH_INCOMPLETE':'หุ้นยังไม่นำทั้ง SPY และกลุ่มครบสองช่วง',
      'TREND_UNCONFIRMED':'แนวโน้มยังไม่ยืนยัน','OUTSIDE_TRIGGER_ZONE':'ราคายังอยู่นอกเขตอ้างอิงเข้า',
      'VOLUME_CONFIRMATION_MISSING':'ปริมาณ IEX ยังไม่ยืนยัน','NO_OBSERVED_RESISTANCE_TARGET':'ยังไม่มีแนวต้านเดิมเหนือ trigger ให้ประเมินเป้าหมาย',
      'NET_REWARD_RISK_BELOW_2':'ผลตอบแทนต่อความเสี่ยงหลังต้นทุนต่ำกว่า 2','EXCESS_VOLATILITY':'ความผันผวนสูงเกินเกณฑ์',
      'BELOW_LONG_TREND':'ราคาต่ำกว่าแนวโน้มระยะยาว','OVEREXTENDED':'ราคาไกลจากจุดอ้างอิงเกินเกณฑ์',
      'LOW_IEX_LIQUIDITY':'กิจกรรมซื้อขาย IEX ต่ำเกินเกณฑ์','ALL_RESEARCH_GATES_PASSED':'ผ่านเกณฑ์เพื่อทบทวน ยังไม่ใช่คำสั่งซื้อ'}
    app.context_processor(lambda:{'stock_data':current(),'stock_universe':universe,'stock_reason_labels':labels})
    return current
