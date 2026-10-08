"""
AI Market Radar V5.2 - Trigger Monitor V1

Isolated presentation/runtime extension on top of V5.1.
Existing Scanner, Multi-Radar, Premarket Gate, Opening Confirmation,
Final Decision and Position Engine are not modified.

Trigger Monitor is read-only / alert-only. It never sends orders.
"""

import scanner_v510 as v510
import os
import threading
import time
from flask import jsonify, request

from trigger_monitor import get_intraday_quote
from telegram_alerts import send_entry_alert, telegram_configured, send_test_message

app = v510.app


@app.route("/api/trigger-quote")
def _v520_trigger_quote_api():
    try:
        ticker = str(request.args.get("ticker") or "").strip().upper()
        force = str(request.args.get("force") or "").lower() in {"1", "true", "yes"}
        return jsonify({"ok": True, "data": get_intraday_quote(ticker, force=force)})
    except Exception as exc:
        return jsonify({"ok": False, "version": "5.2-trigger-monitor", "error": str(exc)}), 200


@app.route("/api/telegram-health")
def _v520_telegram_health_api():
    return jsonify({"ok": True, "configured": telegram_configured()})


@app.route("/api/telegram-entry-alert", methods=["POST"])
def _v520_telegram_entry_alert_api():
    try:
        payload = request.get_json(silent=True) or {}
        ticker = str(payload.get("ticker") or "").strip().upper()
        entry = payload.get("entry")
        buy_low = payload.get("buy_low")
        buy_high = payload.get("buy_high")
        opening = str(payload.get("opening") or "").upper()
        final_status = str(payload.get("final_status") or "").upper()

        if not ticker or entry is None or buy_low is None or buy_high is None:
            return jsonify({"ok": False, "error": "missing_signal_fields"}), 400

        entry_f = float(entry)
        low_f = float(buy_low)
        high_f = float(buy_high)
        if low_f <= 0 or high_f < low_f or entry_f < low_f or entry_f > high_f * 1.005:
            return jsonify({"ok": False, "error": "entry_outside_allowed_zone"}), 400

        if opening != "ENTRY1" or final_status != "CONFIRMED":
            return jsonify({"ok": False, "error": "signal_not_confirmed"}), 400

        result = send_entry_alert(payload)
        code = 200 if result.get("ok") else 503
        return jsonify(result), code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


_TRIGGER_MONITOR_UI = r"""
<style id="v520TriggerStyle">
.v520Card{margin-top:14px;border:1px solid #315a7e;border-radius:18px;padding:14px;background:#0b2135}
.v520Head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.v520Badge{font-size:10px;font-weight:900;padding:5px 8px;border-radius:20px;background:#173d5e;border:1px solid #39749f;color:#c9e4f8}
.v520Grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}
.v520Metric{background:#112b43;border-radius:13px;padding:10px}.v520Metric span{display:block;font-size:10px;color:#9eb1c6}.v520Metric b{display:block;margin-top:3px;font-size:16px}
.v520Actions{display:flex;gap:8px;margin-top:10px}.v520Actions button{margin:0;flex:1}
.v520Note{margin-top:9px;font-size:10px;color:#8fa9c1;line-height:1.5}
@media(max-width:560px){.v520Grid{grid-template-columns:1fr 1fr}.v520Metric:last-child{grid-column:1/-1}}
</style>
<script id="v520TriggerMonitor">
(function(){
  var M={armed:false,ticker:null,trigger:null,buyHigh:null,hits:0,timer:null,lastFinal:null,lastOpening:null,lastQuote:null};

  function money(v){
    var n=Number(v); return Number.isFinite(n)?'$'+n.toFixed(2):'—';
  }
  function text(id,v){var e=document.getElementById(id);if(e)e.textContent=v}
  function status(msg,cls){
    var e=document.getElementById('v520Status');if(!e)return;
    e.className='status '+(cls||'info');e.innerHTML=msg;
  }
  function ensure(){
    if(document.getElementById('v520TriggerCard'))return;
    var anchor=document.getElementById('finalDash');
    if(!anchor)return;
    var card=document.createElement('section');
    card.id='v520TriggerCard';card.className='v520Card';
    card.innerHTML=
      '<div class="v520Head"><div><b>⚡ Trigger Monitor</b><div class="small" style="margin-top:4px">WATCH → Trigger → Recheck อัตโนมัติ</div></div><span class="v520Badge">V5.2</span></div>'+
      '<div id="v520Status" class="status info" style="margin-top:10px">⚪ ยังไม่ได้เปิด Monitor</div>'+
      '<div class="v520Grid">'+
        '<div class="v520Metric"><span>หุ้น</span><b id="v520Ticker">—</b></div>'+
        '<div class="v520Metric"><span>Trigger</span><b id="v520Trigger">—</b></div>'+
        '<div class="v520Metric"><span>ราคาล่าสุด</span><b id="v520Price">—</b></div>'+
      '</div>'+
      '<div class="v520Actions"><button id="v520Arm" type="button">▶ เริ่มเฝ้า Trigger</button><button id="v520Stop" class="alt" type="button">■ หยุด</button></div>'+
      '<div class="v520Note">Alert only • ต้องเปิดหน้านี้ไว้ • ใช้ราคานาทีจากแหล่งข้อมูลฟรี จึงอาจช้ากว่า Webull • ระบบไม่ส่งคำสั่งซื้อ</div>';
    anchor.parentNode.insertBefore(card,anchor.nextSibling);
    document.getElementById('v520Arm').addEventListener('click',arm);
    document.getElementById('v520Stop').addEventListener('click',stop);
  }

  function syncCandidate(){
    ensure();
    try{
      if(typeof selected!=='undefined' && selected){
        M.ticker=selected.ticker||null;
        M.trigger=Number(selected.buy_low);
        M.buyHigh=Number(selected.buy_high);
        text('v520Ticker',M.ticker||'—');
        text('v520Trigger',money(M.trigger));
      }
    }catch(e){}
  }

  function stop(){
    M.armed=false;M.hits=0;
    if(M.timer){clearTimeout(M.timer);M.timer=null}
    status('⚪ Monitor หยุดแล้ว','info');
  }

  function arm(){
    syncCandidate();
    if(!M.ticker || !Number.isFinite(M.trigger) || !Number.isFinite(M.buyHigh)){
      status('🔴 ยังไม่มีหุ้น/Buy Zone สำหรับ Monitor','bad');return;
    }
    M.armed=true;M.hits=0;
    status('<b>🟡 ARMED</b> • กำลังเฝ้า '+M.ticker+' ที่ '+money(M.trigger),'warn');
    poll(true);
  }

  async function quote(force){
    var r=await fetch('/api/trigger-quote?ticker='+encodeURIComponent(M.ticker)+(force?'&force=1':''),{cache:'no-store'});
    var j=await r.json();
    if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
    return j.data||{};
  }

  function getNum(id){
    var e=document.getElementById(id);
    if(!e)return null;
    var raw=String(e.value==null?'':e.value).trim();
    if(raw==='')return null;
    var n=Number(raw.replace(',','.').replace('%',''));
    return Number.isFinite(n)?n:null;
  }

  async function rerunOpening(price){
    if(typeof ensureContext!=='function')return {state:'NO_CONTEXT'};
    var ctx=await ensureContext(); if(!ctx)return {state:'NO_CONTEXT'};
    var op=getNum('openPrice'), hi=getNum('openingHigh'), lo=getNum('openingLow');
    if(!(op>0&&hi>0&&lo>0))return {state:'NEED_OPENING_INPUT'};
    hi=Math.max(hi,price);lo=Math.min(lo,price);
    var rv=getNum('openingRV'),pm=getNum('premarketPct');
    var sg=(ctx.groups&&selected&&ctx.groups[selected.group])||{state:'unknown'};
    var body={
      price:price,open_price:op,opening_high:hi,opening_low:lo,
      buy_low:selected.buy_low,buy_high:selected.buy_high,stop:selected.stop,tp1:selected.tp1,
      premarket_pct:pm,rel_volume:rv,market:ctx.market,sector:sg.state,
      catalyst:(typeof catalyst!=='undefined'&&catalyst&&catalyst.sentiment)||'unknown',
      catalyst_score:(typeof catalyst!=='undefined'&&catalyst&&catalyst.score!=null)?catalyst.score:50,
      negative_high_impact:!!(typeof catalyst!=='undefined'&&catalyst&&catalyst.negative_high_impact),
      data_confidence:selected.confidence_code||'FRESH'
    };
    var r=await fetch('/api/opening-confirm',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify(body)});
    var j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
    if(typeof renderOpening==='function')renderOpening(j.data||{});
    M.lastOpening=j.data||{};
    return M.lastOpening;
  }

  async function rerunFinal(price){
    var ctx=await ensureContext();if(!ctx)return {status:'NO_CONTEXT'};
    var pm=getNum('premarketPct'),rv=getNum('relVolume');
    var sg=(ctx.groups&&selected&&ctx.groups[selected.group])||{state:'unknown'};
    var body={
      price:price,buy_low:selected.buy_low,buy_high:selected.buy_high,stop:selected.stop,tp1:selected.tp1,
      data_confidence:selected.confidence_code,market:ctx.market,sector:sg.state,
      catalyst:(catalyst&&catalyst.sentiment)||'unknown',catalyst_score:(catalyst&&catalyst.score!=null)?catalyst.score:50,
      negative_high_impact:!!(catalyst&&catalyst.negative_high_impact),premarket_pct:pm,rel_volume:rv
    };
    var r=await fetch('/api/auto-confirm',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify(body)});
    var j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
    if(typeof renderFinalDecision==='function')renderFinalDecision(j.data||{},price);
    M.lastFinal=j.data||{};
    return M.lastFinal;
  }

  async function sendTelegramEntry(price,op,fd){
    try{
      var ctx=(typeof context!=='undefined'&&context)||{};
      var sg=(ctx.groups&&selected&&ctx.groups[selected.group])||{};
      var payload={
        ticker:M.ticker,
        entry:price,
        buy_low:selected.buy_low,
        buy_high:selected.buy_high,
        score:fd&&fd.score,
        opening:op&&op.state,
        final_status:fd&&fd.status,
        market:ctx.market||'unknown',
        group:sg.state||'unknown',
        time_label:new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})
      };
      var r=await fetch('/api/telegram-entry-alert',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        cache:'no-store',
        body:JSON.stringify(payload)
      });
      var j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||j.reason||('HTTP '+r.status));
      return j;
    }catch(e){
      return {ok:false,error:e.message};
    }
  }

  function notify(msg){
    try{if(navigator.vibrate)navigator.vibrate([200,100,200])}catch(e){}
    try{
      if(window.Notification&&Notification.permission==='granted')new Notification('AI Radar Trigger',{body:msg});
    }catch(e){}
  }

  async function poll(force){
    if(!M.armed)return;
    try{
      var q=await quote(force);M.lastQuote=q;
      var p=Number(q.price);text('v520Price',money(p));
      if(!Number.isFinite(p))throw Error('ราคาไม่ถูกต้อง');
      if(q.age_seconds!=null && Number(q.age_seconds)>300){
        M.hits=0;status('⚪ ราคาจากแหล่งข้อมูลฟรีเก่าเกิน 5 นาที • ยังไม่ยืนยัน Trigger','info');
      }else if(p<M.trigger){
        M.hits=0;status('<b>🟡 WATCH</b> • '+M.ticker+' '+money(p)+' • รอ '+money(M.trigger),'warn');
      }else if(p>M.buyHigh*1.005){
        M.hits=0;status('<b>🟠 DONT CHASE</b> • '+money(p)+' พ้น Buy Zone '+money(M.buyHigh)+' แล้ว','warn');
      }else{
        M.hits+=1;
        if(M.hits<2){
          status('<b>🟡 TRIGGER TOUCHED</b> • '+money(p)+' • รอยืนยันรอบถัดไป','warn');
        }else{
          var op=await rerunOpening(p);
          if(op.state==='NEED_OPENING_INPUT'){
            status('<b>🟡 TRIGGER CONFIRMED</b> • กรุณากรอก Opening Check 1 ครั้งเพื่อให้ Monitor ตรวจต่ออัตโนมัติ','warn');
          }else if(op.state==='INVALIDATED'){
            status('<b>🔴 REJECTED</b> • Opening structure ถูกยกเลิก','bad');M.hits=0;
          }else if(op.state==='ENTRY1'){
            var fd=await rerunFinal(p);
            if(fd.status==='CONFIRMED'){
              status('<b>🟢 ENTRY 1 CONFIRMED</b> • '+M.ticker+' '+money(p)+' • Opening + Final ผ่าน','good');
              notify(M.ticker+' Entry 1 confirmed at '+money(p));
              sendTelegramEntry(p,op,fd).then(function(tg){
                if(tg&&tg.ok&&tg.sent){
                  status('<b>🟢 ENTRY 1 CONFIRMED</b> • '+M.ticker+' '+money(p)+' • ส่ง Telegram แล้ว','good');
                }
              });
            }else{
              status('<b>🟡 TRIGGER ผ่าน แต่ Final ยังไม่ผ่าน</b> • '+(fd.label||fd.status||'WAIT'),'warn');
            }
          }else{
            status('<b>🔵 Trigger ผ่าน</b> • Opening '+(op.label||op.state||'ยังรอยืนยัน')+' • ระบบจะตรวจต่อ','info');
          }
        }
      }
    }catch(e){
      status('⚪ Trigger Monitor อ่านราคาไม่ได้: '+e.message+' • จะลองใหม่','info');
    }
    if(M.armed)M.timer=setTimeout(function(){poll(false)},20000);
  }

  function hook(){
    ensure();syncCandidate();
    if(!window.__v520RenderFinalHook && typeof renderFinalDecision==='function'){
      var oldFinal=renderFinalDecision;
      renderFinalDecision=function(x,p){var out=oldFinal(x,p);M.lastFinal=x||{};syncCandidate();return out};
      window.__v520RenderFinalHook=true;
    }
    if(!window.__v520RenderOpeningHook && typeof renderOpening==='function'){
      var oldOpen=renderOpening;
      renderOpening=function(x){var out=oldOpen(x);M.lastOpening=x||{};syncCandidate();return out};
      window.__v520RenderOpeningHook=true;
    }
  }

  function boot(){
    hook();
    if(window.Notification&&Notification.permission==='default'){
      var b=document.getElementById('v520Arm');
      if(b)b.addEventListener('click',function(){Notification.requestPermission().catch(function(){})},{once:true});
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(hook,900);
})();
</script>
"""


@app.after_request
def _v520_inject_trigger_monitor(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v520TriggerMonitor" not in body:
                pos = body.lower().rfind("</body>")
                if pos >= 0:
                    body = body[:pos] + _TRIGGER_MONITOR_UI + "\n" + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response


if os.getenv("TELEGRAM_TEST_ON_BOOT") == "1":
    def _telegram_boot_test():
        time.sleep(3)
        send_test_message()
    threading.Thread(target=_telegram_boot_test, daemon=True).start()
