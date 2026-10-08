import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import storage
from config import BOT_USERNAME

POLL_MS=1200

class AuthApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Secure Pharmacy IS")
        self.geometry("1050x700")
        self.minsize(900,600)
        self.user=None
        self.frames={}
        container=ttk.Frame(self); container.pack(fill="both",expand=True)
        for F in (LoginFrame,RegisterFrame,BindFrame,PushFrame,ResetFrame,MainFrame):
            f=F(container,self); self.frames[F.__name__]=f; f.grid(row=0,column=0,sticky="nsew")
        container.rowconfigure(0,weight=1); container.columnconfigure(0,weight=1)
        self.show_frame("LoginFrame")

    def show_frame(self,name,**kw):
        f=self.frames[name]
        if hasattr(f,"on_show"): f.on_show(**kw)
        f.tkraise()

    def show_admin_password(self,p):
        messagebox.showwarning("Первый запуск","Создан единственный администратор.\n\nЛогин: admin\nПароль: "+p+
                               "\n\nСохраните пароль. В открытом виде он больше не хранится.")

class LoginFrame(ttk.Frame):
    def __init__(self,p,c):
        super().__init__(p); self.c=c
        ttk.Label(self,text="Вход в систему",font=("Segoe UI",22,"bold")).pack(pady=(80,25))
        box=ttk.Frame(self); box.pack()
        self.login=tk.StringVar(); self.password=tk.StringVar()
        ttk.Label(box,text="Логин").grid(row=0,column=0,padx=8,pady=8,sticky="e")
        ttk.Entry(box,textvariable=self.login,width=30).grid(row=0,column=1,pady=8)
        ttk.Label(box,text="Пароль").grid(row=1,column=0,padx=8,pady=8,sticky="e")
        ttk.Entry(box,textvariable=self.password,show="•",width=30).grid(row=1,column=1,pady=8)
        self.err=ttk.Label(self,text="",foreground="red"); self.err.pack(pady=10)
        ttk.Button(self,text="Войти",command=self.login_click).pack(pady=5)
        ttk.Button(self,text="Зарегистрироваться",command=lambda:c.show_frame("RegisterFrame")).pack(pady=5)
        ttk.Button(self,text="Восстановить пароль",command=lambda:c.show_frame("ResetFrame")).pack(pady=5)

    def on_show(self): self.err.config(text=""); self.password.set("")
    def login_click(self):
        l=self.login.get().strip(); p=self.password.get()
        if not l or not p: self.err.config(text="Заполните поля."); return
        if not storage.user_exists(l) or not storage.check_credentials(l,p):
            self.err.config(text="Неверный логин или пароль."); return
        if not storage.get_telegram_id(l):
            code=storage.create_bind_session(l); self.c.show_frame("BindFrame",login=l,code=code,purpose="login"); return
        sid=storage.create_push_session(l,"login")
        if not sid: self.err.config(text="Не удалось создать запрос."); return
        self.c.show_frame("PushFrame",login=l,session_id=sid,kind="login")

class RegisterFrame(ttk.Frame):
    def __init__(self,p,c):
        super().__init__(p); self.c=c
        ttk.Label(self,text="Регистрация",font=("Segoe UI",22,"bold")).pack(pady=(70,25))
        box=ttk.Frame(self); box.pack()
        self.login=tk.StringVar(); self.p1=tk.StringVar(); self.p2=tk.StringVar()
        for i,(t,v) in enumerate([("Логин",self.login),("Пароль",self.p1),("Повтор",self.p2)]):
            ttk.Label(box,text=t).grid(row=i,column=0,padx=8,pady=8,sticky="e")
            ttk.Entry(box,textvariable=v,show="•" if i else "",width=30).grid(row=i,column=1,pady=8)
        self.err=ttk.Label(self,text="",foreground="red"); self.err.pack(pady=10)
        ttk.Button(self,text="Создать аккаунт",command=self.reg).pack(pady=5)
        ttk.Button(self,text="Назад",command=lambda:c.show_frame("LoginFrame")).pack(pady=5)
    def on_show(self): self.err.config(text="")
    def reg(self):
        l=self.login.get().strip(); p=self.p1.get()
        if not l or len(p)<6 or p!=self.p2.get(): self.err.config(text="Проверьте логин и пароли."); return
        if storage.user_exists(l): self.err.config(text="Логин уже занят."); return
        storage.create_user(l,p); code=storage.create_bind_session(l)
        self.c.show_frame("BindFrame",login=l,code=code,purpose="register")

class BindFrame(ttk.Frame):
    def __init__(self,p,c):
        super().__init__(p); self.c=c; self.job=None
        ttk.Label(self,text="Привязка Telegram",font=("Segoe UI",22,"bold")).pack(pady=(70,20))
        self.info=ttk.Label(self,justify="center",wraplength=700); self.info.pack(pady=15)
        self.code=ttk.Label(self,font=("Consolas",28,"bold")); self.code.pack(pady=15)
        self.status=ttk.Label(self); self.status.pack(pady=10)
        ttk.Button(self,text="Новый код",command=self.new_code).pack(pady=5)
        ttk.Button(self,text="Отмена",command=lambda:c.show_frame("LoginFrame")).pack(pady=5)
    def on_show(self,login,code,purpose):
        self.login=login; self.code_value=code; self.purpose=purpose
        self.info.config(text=f"Откройте @{BOT_USERNAME} в Telegram и отправьте код ниже.\n"
                              "Код нужен только для первичной привязки Telegram.")
        self.code.config(text=code); self.status.config(text="Ожидание...")
        self.poll()
    def new_code(self): self.code_value=storage.create_bind_session(self.login); self.code.config(text=self.code_value); self.poll()
    def poll(self):
        if self.job: self.after_cancel(self.job)
        s=storage.get_bind_session_status(self.code_value)
        if s=="confirmed":
            if self.purpose=="register": messagebox.showinfo("Готово","Telegram привязан. Роль аккаунта: сотрудник.")
            if self.purpose=="login":
                sid=storage.create_push_session(self.login,"login"); self.c.show_frame("PushFrame",login=self.login,session_id=sid,kind="login"); return
            self.c.show_frame("LoginFrame"); return
        if s in ("expired","rejected"): self.status.config(text="Код недействителен. Создайте новый.",foreground="red"); return
        self.job=self.after(POLL_MS,self.poll)

class PushFrame(ttk.Frame):
    def __init__(self,p,c):
        super().__init__(p); self.c=c; self.job=None
        ttk.Label(self,text="Подтверждение Telegram",font=("Segoe UI",22,"bold")).pack(pady=(100,20))
        self.info=ttk.Label(self,justify="center",wraplength=700); self.info.pack(pady=20)
        self.status=ttk.Label(self,text="Ожидание..."); self.status.pack(pady=15)
        ttk.Button(self,text="Отмена",command=lambda:c.show_frame("LoginFrame")).pack()
    def on_show(self,login,session_id,kind):
        self.login=login; self.sid=session_id; self.kind=kind
        text="вход" if kind=="login" else "восстановление пароля"
        self.info.config(text=f"Запрос на {text} отправлен в Telegram.\nНажмите кнопку в чате с ботом.")
        self.poll()
    def poll(self):
        if self.job: self.after_cancel(self.job)
        s=storage.get_push_session_status(self.sid)
        if s=="confirmed":
            if self.kind=="login": self.c.user=self.login; self.c.show_frame("MainFrame",login=self.login)
            else: self.c.show_frame("ResetFrame",login=self.login,verified=True)
            return
        if s in ("expired","failed","rejected","not_found"):
            self.status.config(text="Запрос завершён без подтверждения.",foreground="red"); return
        self.job=self.after(POLL_MS,self.poll)

class ResetFrame(ttk.Frame):
    def __init__(self,p,c):
        super().__init__(p); self.c=c; self.verified=False
        ttk.Label(self,text="Восстановление пароля",font=("Segoe UI",22,"bold")).pack(pady=(80,20))
        self.login=tk.StringVar(); self.p1=tk.StringVar(); self.p2=tk.StringVar()
        self.box=ttk.Frame(self); self.box.pack()
        ttk.Label(self.box,text="Логин").grid(row=0,column=0,padx=8,pady=8)
        ttk.Entry(self.box,textvariable=self.login,width=30).grid(row=0,column=1)
        self.status=ttk.Label(self,text="",foreground="red"); self.status.pack(pady=10)
        self.btn=ttk.Button(self,text="Отправить подтверждение в Telegram",command=self.request); self.btn.pack(pady=5)
        ttk.Button(self,text="Назад",command=lambda:c.show_frame("LoginFrame")).pack(pady=5)
    def on_show(self,login=None,verified=False):
        if login: self.login.set(login)
        self.verified=verified
        if verified: self.show_new_password()
        else: self.status.config(text="")
    def request(self):
        l=self.login.get().strip()
        if not storage.user_exists(l): self.status.config(text="Пользователь не найден."); return
        if not storage.get_telegram_id(l): self.status.config(text="У аккаунта нет привязанного Telegram."); return
        sid=storage.create_push_session(l,"reset"); self.c.show_frame("PushFrame",login=l,session_id=sid,kind="reset")
    def show_new_password(self):
        for w in self.box.winfo_children(): w.destroy()
        ttk.Label(self.box,text="Новый пароль").grid(row=0,column=0,padx=8,pady=8)
        ttk.Entry(self.box,textvariable=self.p1,show="•",width=30).grid(row=0,column=1)
        ttk.Label(self.box,text="Повтор").grid(row=1,column=0,padx=8,pady=8)
        ttk.Entry(self.box,textvariable=self.p2,show="•",width=30).grid(row=1,column=1)
        ttk.Button(self,text="Сохранить пароль",command=self.save).pack(pady=5)
        self.status.config(text="Telegram подтверждён.",foreground="green")
    def save(self):
        if len(self.p1.get())<6 or self.p1.get()!=self.p2.get(): self.status.config(text="Пароли не совпадают или слишком короткие."); return
        storage.reset_password(self.login.get().strip(),self.p1.get())
        storage.log_action(self.login.get().strip(),"Восстановление пароля")
        messagebox.showinfo("Готово","Пароль изменён."); self.c.show_frame("LoginFrame")

class MainFrame(ttk.Frame):
    def __init__(self,p,c):
        super().__init__(p); self.c=c
    def on_show(self,login):
        self.login=login; self.role=storage.get_role(login)
        self.build()
    def build(self):
        for w in self.winfo_children(): w.destroy()
        top=ttk.Frame(self); top.pack(fill="x",padx=15,pady=12)
        ttk.Label(top,text=f"ИC «База данных аптеки» | {self.login} | {self.role}",font=("Segoe UI",15,"bold")).pack(side="left")
        ttk.Button(top,text="Выйти",command=self.logout).pack(side="right")
        tabs=ttk.Notebook(self); tabs.pack(fill="both",expand=True,padx=10,pady=5)
        self.dashboard_tab(tabs); self.pharmacy_tab(tabs); self.sales_tab(tabs)
        if self.role==storage.ROLE_ADMIN:
            self.users_tab(tabs); self.audit_tab(tabs)
    def dashboard_tab(self,tabs):
        f=ttk.Frame(tabs); tabs.add(f,text="Главная")
        s=storage.get_dashboard_stats()
        for i,(k,v) in enumerate([("Видов лекарств",s["medicine_types"]),("Единиц на складе",s["units"]),
                                  ("Мало товара",s["low_stock"]),("Продажи сегодня",f'{s["today_sales"]:.2f} ₸'),
                                  ("Чеков сегодня",s["today_receipts"])]):
            ttk.Label(f,text=k,font=("Segoe UI",11)).grid(row=0,column=i,padx=15,pady=(60,5))
            ttk.Label(f,text=str(v),font=("Segoe UI",20,"bold")).grid(row=1,column=i,padx=15)
    def pharmacy_tab(self,tabs):
        f=ttk.Frame(tabs); tabs.add(f,text="Лекарства")
        cols=("name","manufacturer","category","price","quantity","expiry")
        tree=ttk.Treeview(f,columns=cols,show="headings")
        heads={"name":"Название","manufacturer":"Производитель","category":"Категория","price":"Цена","quantity":"Остаток","expiry":"Срок годности"}
        for c in cols: tree.heading(c,text=heads[c]); tree.column(c,width=140)
        tree.pack(fill="both",expand=True,padx=10,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for m in storage.list_medicines(): tree.insert("", "end",iid=m["id"],values=(m["name"],m["manufacturer"],m["category"],f'{m["price"]:.2f}',m["quantity"],m["expiry"]))
        def sell():
            sel=tree.selection()
            if not sel: return
            self.sale_dialog(sel[0],refresh)
        ttk.Button(f,text="Оформить продажу",command=sell).pack(pady=5)
        if self.role==storage.ROLE_ADMIN:
            ttk.Button(f,text="Добавить лекарство",command=lambda:self.medicine_dialog(refresh)).pack(pady=5)
            ttk.Button(f,text="Удалить выбранное",command=lambda:self.delete_medicine(tree,refresh)).pack(pady=5)
        refresh()
    def sale_dialog(self,mid,refresh):
        w=tk.Toplevel(self); w.title("Продажа"); w.geometry("320x180")
        ttk.Label(w,text="Количество").pack(pady=15); q=tk.StringVar(value="1"); ttk.Entry(w,textvariable=q).pack()
        def go():
            ok,msg,_=storage.record_sale(mid,q.get(),self.login)
            if ok: storage.log_action(self.login,"Продажа",msg); messagebox.showinfo("Продажа",msg); refresh(); w.destroy()
            else: messagebox.showerror("Ошибка",msg)
        ttk.Button(w,text="Оформить",command=go).pack(pady=15)
    def medicine_dialog(self,refresh,mid=None):
        m=storage.get_medicine(mid) if mid else None
        w=tk.Toplevel(self); w.title("Лекарство"); w.geometry("400x430")
        vars=[tk.StringVar(value=str(m.get(k,"")) if m else "") for k in ("name","manufacturer","category","price","quantity","min_stock","expiry")]
        for i,(label,var) in enumerate(zip(["Название","Производитель","Категория","Цена","Количество","Мин. остаток","Срок годности"],vars)):
            ttk.Label(w,text=label).pack(pady=(8,2)); ttk.Entry(w,textvariable=var,width=38).pack()
        def save():
            try:
                if m: storage.update_medicine(mid,*[v.get() for v in vars])
                else: storage.create_medicine(*[vars[0].get(),vars[1].get(),vars[2].get(),float(vars[3].get()),int(vars[4].get()),int(vars[5].get()),vars[6].get()])
                storage.log_action(self.login,"Изменение каталога"); refresh(); w.destroy()
            except Exception as e: messagebox.showerror("Ошибка",str(e))
        ttk.Button(w,text="Сохранить",command=save).pack(pady=15)
    def delete_medicine(self,tree,refresh):
        sel=tree.selection()
        if not sel: return
        if messagebox.askyesno("Удаление","Удалить выбранное лекарство?"):
            storage.delete_medicine(sel[0]); storage.log_action(self.login,"Удаление лекарства"); refresh()
    def sales_tab(self,tabs):
        f=ttk.Frame(tabs); tabs.add(f,text="Продажи")
        tree=ttk.Treeview(f,columns=("time","medicine","qty","total","user"),show="headings")
        for c,h in zip(tree["columns"],["Дата","Лекарство","Кол-во","Сумма","Пользователь"]): tree.heading(c,text=h)
        tree.pack(fill="both",expand=True,padx=10,pady=10)
        for s in storage.list_sales(): tree.insert("", "end",values=(datetime.fromtimestamp(s["created_at"]).strftime("%d.%m.%Y %H:%M"),s["medicine_name"],s["quantity"],f'{s["total"]:.2f} ₸',s["user"]))
    def users_tab(self,tabs):
        f=ttk.Frame(tabs); tabs.add(f,text="Пользователи")
        tree=ttk.Treeview(f,columns=("login","role","tg"),show="headings")
        for c,h in zip(tree["columns"],["Логин","Роль","Telegram"]): tree.heading(c,text=h)
        tree.pack(fill="both",expand=True,padx=10,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for l,u in storage.list_users().items(): tree.insert("", "end",iid=l,values=(l,u["role"],"привязан" if u["telegram_linked"] else "нет"))
        def reset():
            sel=tree.selection()
            if not sel: return
            p=storage.admin_generate_temp_password(sel[0])
            messagebox.showinfo("Временный пароль",f"{sel[0]}: {p}")
        def unbind():
            sel=tree.selection()
            if sel: storage.unbind_telegram(sel[0]); refresh()
        ttk.Button(f,text="Сгенерировать временный пароль",command=reset).pack(pady=5)
        ttk.Button(f,text="Отвязать Telegram",command=unbind).pack(pady=5)
        refresh()
    def audit_tab(self,tabs):
        f=ttk.Frame(tabs); tabs.add(f,text="Журнал")
        tree=ttk.Treeview(f,columns=("time","user","action","details"),show="headings")
        for c,h in zip(tree["columns"],["Дата","Пользователь","Действие","Детали"]): tree.heading(c,text=h)
        tree.pack(fill="both",expand=True,padx=10,pady=10)
        for a in storage.list_audit():
            tree.insert("", "end",values=(datetime.fromtimestamp(a["timestamp"]).strftime("%d.%m.%Y %H:%M:%S"),a["user"],a["action"],a["details"]))
    def logout(self):
        storage.log_action(self.login,"Выход"); self.c.user=None; self.c.show_frame("LoginFrame")
