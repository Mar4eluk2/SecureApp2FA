"""Учебное JSON-хранилище SecureApp2FA + информационная система аптеки."""
import hashlib, json, os, secrets, sys, time
from datetime import datetime, date

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
BIND_SESSIONS_FILE = os.path.join(BASE_DIR, "bind_sessions.json")
PUSH_SESSIONS_FILE = os.path.join(BASE_DIR, "push_sessions.json")
PHARMACY_FILE = os.path.join(BASE_DIR, "pharmacy.json")
SALES_FILE = os.path.join(BASE_DIR, "sales.json")
AUDIT_FILE = os.path.join(BASE_DIR, "audit.json")

ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"
DEFAULT_ADMIN_LOGIN = "admin"
BIND_CODE_TTL_SECONDS = 300
PUSH_SESSION_TTL_SECONDS = {"login": 120, "reset": 300}

DEFAULT_MEDICINES = [
    ["Парацетамол 500 мг","Фармстандарт","Обезболивающие",650,42,10,"2027-11-30"],
    ["Ибупрофен 200 мг","Белмедпрепараты","Обезболивающие",820,35,8,"2028-02-28"],
    ["Амоксициллин 500 мг","Sandoz","Антибиотики",1950,18,5,"2027-07-31"],
    ["Лоратадин 10 мг","Акрихин","Противоаллергические",930,7,8,"2027-05-31"],
    ["Омепразол 20 мг","Dr. Reddy's","Для ЖКТ",1200,23,6,"2028-01-31"],
    ["Хлоргексидин 0,05%","ЮжФарм","Антисептики",480,52,12,"2029-03-31"],
    ["Витамин C 500 мг","Solgar","Витамины",2850,16,5,"2028-09-30"],
    ["Смекта","Ipsen","Для ЖКТ",1450,12,5,"2027-12-31"],
    ["Називин 0,05%","Merck","Противопростудные",1100,9,6,"2027-10-31"],
    ["Мирамистин 150 мл","Инфамед","Антисептики",2450,5,6,"2028-06-30"],
]

def _load(path, default):
    if not os.path.exists(path):
        return default.copy() if isinstance(default, (dict,list)) else default
    try:
        with open(path, encoding="utf-8") as f:
            s=f.read().strip()
            return json.loads(s) if s else default.copy()
    except (OSError, json.JSONDecodeError):
        return default.copy()

def _save(path, data):
    tmp=path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
    os.replace(tmp,path)

def hash_password(password, salt=None):
    salt=salt or secrets.token_hex(16)
    h=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),100_000)
    return h.hex(),salt

def verify_password(password, stored_hash, salt):
    return secrets.compare_digest(hash_password(password,salt)[0],stored_hash)

def load_users(): return _load(USERS_FILE,{})
def save_users(users): _save(USERS_FILE,users)
def user_exists(login): return login in load_users()

def create_user(login,password,role=ROLE_EMPLOYEE):
    users=load_users(); h,s=hash_password(password)
    users[login]={"password_hash":h,"salt":s,"telegram_id":None,"role":ROLE_EMPLOYEE,"created_at":time.time()}
    save_users(users)

def check_credentials(login,password):
    u=load_users().get(login)
    if not u: return False
    try: return verify_password(password,u["password_hash"],u["salt"])
    except (KeyError,TypeError,ValueError): return False

def reset_password(login,new_password):
    users=load_users()
    if login not in users: return False
    h,s=hash_password(new_password); users[login].update(password_hash=h,salt=s,password_changed_at=time.time())
    save_users(users); return True

def admin_generate_temp_password(login):
    p=secrets.token_urlsafe(9)
    return p if reset_password(login,p) else None

def get_role(login): return load_users().get(login,{}).get("role",ROLE_EMPLOYEE)

def list_users():
    return {k:{"role":v.get("role",ROLE_EMPLOYEE),"telegram_linked":bool(v.get("telegram_id"))}
            for k,v in load_users().items()}

def set_role(login,new_role):
    if new_role not in (ROLE_ADMIN,ROLE_EMPLOYEE): return False,"invalid_role"
    users=load_users()
    if login not in users: return False,"not_found"
    current=users[login].get("role",ROLE_EMPLOYEE)
    if current==ROLE_ADMIN and new_role!=ROLE_ADMIN: return False,"last_admin"
    if new_role==ROLE_ADMIN and current!=ROLE_ADMIN and any(v.get("role")==ROLE_ADMIN for v in users.values()):
        return False,"admin_exists"
    users[login]["role"]=new_role; save_users(users); return True,""

def ensure_default_admin():
    users=load_users()
    if any(v.get("role")==ROLE_ADMIN for v in users.values()): return None
    login=DEFAULT_ADMIN_LOGIN
    if login in users:
        users[login]["role"]=ROLE_ADMIN; save_users(users); return None
    p=secrets.token_urlsafe(9); h,s=hash_password(p)
    users[login]={"password_hash":h,"salt":s,"telegram_id":None,"role":ROLE_ADMIN,"created_at":time.time()}
    save_users(users); return p

def get_telegram_id(login): return load_users().get(login,{}).get("telegram_id")
def is_telegram_id_taken(tid): return any(v.get("telegram_id")==tid for v in load_users().values())

def bind_telegram_id(login,tid):
    users=load_users(); u=users.get(login)
    if not u or u.get("telegram_id") or is_telegram_id_taken(tid): return False
    u["telegram_id"]=tid; u["telegram_linked_at"]=time.time(); save_users(users); return True

def unbind_telegram(login):
    users=load_users()
    if login not in users: return False
    users[login]["telegram_id"]=None; save_users(users); return True

def _code():
    return "".join(secrets.choice("0123456789") for _ in range(6))

def create_bind_session(login):
    sessions=_load(BIND_SESSIONS_FILE,{})
    code=_code()
    while code in sessions: code=_code()
    now=time.time(); sessions[code]={"login":login,"expires_at":now+BIND_CODE_TTL_SECONDS,"status":"pending"}
    _save(BIND_SESSIONS_FILE,sessions); return code

def get_bind_session(code): return _load(BIND_SESSIONS_FILE,{}).get(code)

def get_bind_session_status(code):
    sessions=_load(BIND_SESSIONS_FILE,{}); s=sessions.get(code)
    if not s: return "not_found"
    if s["status"]=="pending" and time.time()>s["expires_at"]:
        s["status"]="expired"; _save(BIND_SESSIONS_FILE,sessions)
    return s["status"]

def confirm_bind_session(code,tid):
    sessions=_load(BIND_SESSIONS_FILE,{}); s=sessions.get(code)
    if not s: return False,"not_found"
    if s["status"]!="pending": return False,s["status"]
    if time.time()>s["expires_at"]: s["status"]="expired"; _save(BIND_SESSIONS_FILE,sessions); return False,"expired"
    if not bind_telegram_id(s["login"],tid):
        reason="telegram_taken" if is_telegram_id_taken(tid) else "already_bound"
        s["status"]="rejected"; _save(BIND_SESSIONS_FILE,sessions); return False,reason
    s["status"]="confirmed"; s["telegram_id"]=tid; _save(BIND_SESSIONS_FILE,sessions); return True,""

def create_push_session(login,kind):
    tid=get_telegram_id(login)
    if not tid or kind not in PUSH_SESSION_TTL_SECONDS: return None
    sessions=_load(PUSH_SESSIONS_FILE,{})
    sid=secrets.token_hex(16); now=time.time()
    sessions[sid]={"login":login,"telegram_id":tid,"kind":kind,"created_at":now,
                   "expires_at":now+PUSH_SESSION_TTL_SECONDS[kind],"status":"pending","notified":False}
    _save(PUSH_SESSIONS_FILE,sessions); return sid

def get_push_session(sid): return _load(PUSH_SESSIONS_FILE,{}).get(sid)

def get_push_session_status(sid):
    sessions=_load(PUSH_SESSIONS_FILE,{}); s=sessions.get(sid)
    if not s: return "not_found"
    if s["status"]=="pending" and time.time()>s["expires_at"]:
        s["status"]="expired"; _save(PUSH_SESSIONS_FILE,sessions)
    return s["status"]

def get_unnotified_push_sessions():
    sessions=_load(PUSH_SESSIONS_FILE,{}); result=[]; changed=False; now=time.time()
    for sid,s in sessions.items():
        if s.get("status")!="pending": continue
        if now>s.get("expires_at",0): s["status"]="expired"; changed=True
        elif not s.get("notified"): result.append((sid,dict(s)))
    if changed: _save(PUSH_SESSIONS_FILE,sessions)
    return result

def mark_push_notified(sid):
    sessions=_load(PUSH_SESSIONS_FILE,{})
    if sid in sessions: sessions[sid]["notified"]=True; _save(PUSH_SESSIONS_FILE,sessions)

def mark_push_failed(sid):
    sessions=_load(PUSH_SESSIONS_FILE,{})
    if sid in sessions: sessions[sid]["status"]="failed"; _save(PUSH_SESSIONS_FILE,sessions)

def reject_push_session(sid,tid):
    sessions=_load(PUSH_SESSIONS_FILE,{}); s=sessions.get(sid)
    if not s or s.get("status")!="pending" or s.get("telegram_id")!=tid: return False
    s["status"]="rejected" if time.time()<=s["expires_at"] else "expired"; _save(PUSH_SESSIONS_FILE,sessions)
    return s["status"]=="rejected"

def confirm_push_session(sid,tid):
    sessions=_load(PUSH_SESSIONS_FILE,{}); s=sessions.get(sid)
    if not s or s.get("status")!="pending" or s.get("telegram_id")!=tid: return False
    if time.time()>s["expires_at"]: s["status"]="expired"; _save(PUSH_SESSIONS_FILE,sessions); return False
    s["status"]="confirmed"; s["confirmed_at"]=time.time(); _save(PUSH_SESSIONS_FILE,sessions); return True

# ---------- Аптечная ИС ----------

def load_pharmacy():
    data=_load(PHARMACY_FILE,[])
    if not data:
        data=[]
        for x in DEFAULT_MEDICINES:
            data.append({"id":secrets.token_hex(6),"name":x[0],"manufacturer":x[1],"category":x[2],
                         "price":x[3],"quantity":x[4],"min_stock":x[5],"expiry":x[6],"updated_at":time.time()})
        _save(PHARMACY_FILE,data)
    return data

def list_medicines(): return sorted(load_pharmacy(),key=lambda x:x["name"].lower())
def save_pharmacy(data): _save(PHARMACY_FILE,data)
def get_medicine(mid): return next((m for m in load_pharmacy() if m["id"]==mid),None)

def create_medicine(name,manufacturer,category,price,quantity,min_stock,expiry):
    m={"id":secrets.token_hex(6),"name":name.strip(),"manufacturer":manufacturer.strip(),"category":category.strip(),
       "price":float(price),"quantity":int(quantity),"min_stock":int(min_stock),"expiry":expiry.strip(),"updated_at":time.time()}
    data=load_pharmacy(); data.append(m); save_pharmacy(data); return m

def update_medicine(mid,name,manufacturer,category,price,quantity,min_stock,expiry):
    data=load_pharmacy()
    for m in data:
        if m["id"]==mid:
            m.update(name=name.strip(),manufacturer=manufacturer.strip(),category=category.strip(),price=float(price),
                     quantity=int(quantity),min_stock=int(min_stock),expiry=expiry.strip(),updated_at=time.time())
            save_pharmacy(data); return True
    return False

def delete_medicine(mid):
    data=load_pharmacy(); new=[m for m in data if m["id"]!=mid]
    if len(new)==len(data): return False
    save_pharmacy(new); return True

def load_sales(): return _load(SALES_FILE,[])
def list_sales(limit=200): return sorted(load_sales(),key=lambda x:x.get("created_at",0),reverse=True)[:limit]

def record_sale(mid,qty,user):
    try: qty=int(qty)
    except: return False,"Количество должно быть целым.",None
    if qty<=0: return False,"Количество должно быть больше нуля.",None
    data=load_pharmacy(); m=next((x for x in data if x["id"]==mid),None)
    if not m: return False,"Лекарство не найдено.",None
    if m["quantity"]<qty: return False,f"Недостаточно товара. Остаток: {m['quantity']}.",None
    total=round(m["price"]*qty,2); m["quantity"]-=qty; m["updated_at"]=time.time(); save_pharmacy(data)
    sale={"id":secrets.token_hex(6),"medicine_id":mid,"medicine_name":m["name"],"quantity":qty,
          "unit_price":m["price"],"total":total,"user":user,"created_at":time.time()}
    sales=load_sales(); sales.append(sale); _save(SALES_FILE,sales); return True,"Продажа оформлена.",sale

def get_dashboard_stats():
    data=load_pharmacy(); sales=load_sales(); start=datetime.combine(date.today(),datetime.min.time()).timestamp()
    today=[s for s in sales if s.get("created_at",0)>=start]
    return {"medicine_types":len(data),"units":sum(int(m["quantity"]) for m in data),
            "low_stock":sum(1 for m in data if int(m["quantity"])<=int(m["min_stock"])),
            "today_sales":round(sum(float(s["total"]) for s in today),2),"today_receipts":len(today)}

def log_action(user,action,details=""):
    a=_load(AUDIT_FILE,[]); a.append({"id":secrets.token_hex(6),"timestamp":time.time(),"user":user,"action":action,"details":details})
    _save(AUDIT_FILE,a[-1000:])

def list_audit(limit=200): return sorted(_load(AUDIT_FILE,[]),key=lambda x:x.get("timestamp",0),reverse=True)[:limit]

def ensure_data():
    load_pharmacy()
    if not os.path.exists(SALES_FILE): _save(SALES_FILE,[])
    if not os.path.exists(AUDIT_FILE): _save(AUDIT_FILE,[])
