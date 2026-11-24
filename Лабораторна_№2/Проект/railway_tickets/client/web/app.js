"use strict";
/* =====================================================================
   Інтерфейс клієнта: прив'язка даних (data binding), вікна та діалоги.
   Логіка роботи з сервером - у client.py (Python), сюди приходять
   лише готові відповіді {ok, message, data}.
   ===================================================================== */

/* ---------------- Обмін з Python-частиною клієнта ---------------- */
async function api(action, body) {
  try {
    const resp = await fetch("/api/" + action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return await resp.json();
  } catch (e) {
    return { ok: false, code: "GUI_OFFLINE", message: "Клієнтська програма (client.py) не відповідає. Перезапустіть її." };
  }
}

/* ---------------- Базовий клас для прив'язки даних ---------------- */
class BindableBase {
  constructor() { this._listeners = []; }
  onPropertyChanged(fn) { this._listeners.push(fn); }
  notify(name) { this._listeners.forEach(fn => fn(name)); }
  /** Змінює поле і повідомляє інтерфейс; використовується в усіх set-методах */
  setField(field, value, ...props) {
    if (this[field] === value) return;
    this[field] = value;
    props.forEach(p => this.notify(p));
    this.notify("*");
  }
}

/** Прив'язує елементи шаблону до властивостей view-моделі */
function bind(root, vm) {
  const listAttrs = ["data-list", "data-seats", "data-stars"];
  const refresh = () => {
    root.querySelectorAll("[data-text]").forEach(el => {
      const v = vm[el.dataset.text];
      el.textContent = v === undefined || v === null ? "" : v;
    });
    root.querySelectorAll("[data-show]").forEach(el => { el.style.display = vm[el.dataset.show] ? "" : "none"; });
    root.querySelectorAll("[data-enabled]").forEach(el => { el.disabled = !vm[el.dataset.enabled]; });
    root.querySelectorAll("[data-bind]").forEach(el => {
      const v = vm[el.dataset.bind];
      if (el.type === "radio") el.checked = el.value === v;
      else if (document.activeElement !== el && el.value !== (v ?? "")) el.value = v ?? "";
    });
  };
  const renderLists = () => listAttrs.forEach(a => root.querySelectorAll("[" + a + "]").forEach(el => {
    const name = el.getAttribute(a);
    vm["render_" + name](el, vm[name]);
  }));
  // інтерфейс -> модель
  root.querySelectorAll("[data-bind]").forEach(el => {
    const ev = el.type === "radio" || el.type === "date" ? "change" : "input";
    el.addEventListener(ev, () => { if (el.type !== "radio" || el.checked) vm[el.dataset.bind] = el.value; });
    if (el.tagName === "INPUT") el.addEventListener("keydown", e => { if (e.key === "Enter" && vm.onEnter) vm.onEnter(); });
  });
  root.querySelectorAll("[data-action]").forEach(el => el.addEventListener("click", e => {
    e.preventDefault();
    vm[el.dataset.action]();
  }));
  // модель -> інтерфейс
  vm.onPropertyChanged(name => {
    if (name === "*") { refresh(); return; }
    listAttrs.forEach(a => root.querySelectorAll("[" + a + "='" + name + "']").forEach(el => vm["render_" + name](el, vm[name])));
  });
  refresh();
  renderLists();
}

/* ---------------- Менеджер вікон ---------------- */
const WindowNavigator = {
  /** Замінює головне вікно (вхід / реєстрація / пошук) */
  show(templateId, vm) {
    const desktop = document.getElementById("desktop");
    desktop.innerHTML = "";
    const node = document.getElementById(templateId).content.firstElementChild.cloneNode(true);
    desktop.appendChild(node);
    bind(node, vm);
    if (vm.loaded) vm.loaded();
    const first = node.querySelector("input:not([type=radio])");
    if (first) first.focus();
  },
  /** Відкриває модальний діалог поверх поточного вікна; повертає Promise з результатом */
  dialog(templateId, vm) {
    return new Promise(resolve => {
      const overlay = document.createElement("div");
      overlay.className = "overlay";
      const node = document.getElementById(templateId).content.firstElementChild.cloneNode(true);
      overlay.appendChild(node);
      document.body.appendChild(overlay);
      vm.closeDialog = result => { overlay.remove(); resolve(result); };
      bind(node, vm);
      if (vm.loaded) vm.loaded();
    });
  },
};

class MessageBoxViewModel extends BindableBase {
  constructor(kind, title, text) {
    super();
    this._kind = kind; this._title = title; this._text = text;
  }
  get title() { return this._title; }
  get text() { return this._text; }
  get icon() { return { info: "✅", error: "⛔", warn: "⚠️", confirm: "❓" }[this._kind]; }
  get isConfirm() { return this._kind === "confirm"; }
  get yesText() { return this.isConfirm ? "Так" : "OK"; }
  yes() { this.closeDialog(true); }
  no() { this.closeDialog(false); }
}
const MessageBox = {
  info: (text, title = "Інформація") => WindowNavigator.dialog("tpl-message", new MessageBoxViewModel("info", title, text)),
  error: (text, title = "Помилка") => WindowNavigator.dialog("tpl-message", new MessageBoxViewModel("error", title, text)),
  confirm: (text, title = "Підтвердження") => WindowNavigator.dialog("tpl-message", new MessageBoxViewModel("confirm", title, text)),
};

/** Якщо сесія закінчилась - повертаємось на вхід */
async function handleFailure(res) {
  if (res.code === "UNAUTHORIZED") {
    await MessageBox.error(res.message, "Сесія завершена");
    WindowNavigator.show("tpl-login", new LoginViewModel());
    return true;
  }
  return false;
}

const stars = n => n ? "★".repeat(Math.round(n)) + "☆".repeat(5 - Math.round(n)) : "—";
const money = v => Number(v).toFixed(2);
const td = (text, cls) => { const c = document.createElement("td"); c.textContent = text; if (cls) c.className = cls; return c; };

/* ---------------- Вікно входу ---------------- */
class LoginViewModel extends BindableBase {
  constructor() { super(); this._login = ""; this._password = ""; this._error = ""; this._busy = false; this._status = ""; }
  get login() { return this._login; }
  set login(v) { this.setField("_login", v.trim()); }
  get password() { return this._password; }
  set password(v) { this.setField("_password", v); }
  get error() { return this._error; }
  set error(v) { this.setField("_error", v); }
  get status() { return this._status; }
  set status(v) { this.setField("_status", v); }
  get notBusy() { return !this._busy; }
  async loaded() {
    const res = await api("session");
    if (res.ok) this.status = "Сервер: " + res.data.server;
  }
  onEnter() { this.submit(); }
  goRegister() { WindowNavigator.show("tpl-register", new RegisterViewModel()); }
  async submit() {
    this.error = "";
    this.setField("_busy", true);
    try {
      const res = await api("login", { login: this.login, password: this.password });
      if (!res.ok) { this.error = res.message; return; }
      WindowNavigator.show("tpl-main", new MainViewModel(res.data.login, res.data.fullName));
    } finally { this.setField("_busy", false); }
  }
}

/* ---------------- Вікно реєстрації ---------------- */
class RegisterViewModel extends BindableBase {
  constructor() {
    super();
    this._fullName = ""; this._login = ""; this._password = ""; this._confirmPassword = "";
    this._error = ""; this._busy = false; this._status = "Пароль: мінімум 8 символів, літери та цифри";
  }
  get fullName() { return this._fullName; }
  set fullName(v) { this.setField("_fullName", v); }
  get login() { return this._login; }
  set login(v) { this.setField("_login", v.trim()); }
  get password() { return this._password; }
  set password(v) { this.setField("_password", v); }
  get confirmPassword() { return this._confirmPassword; }
  set confirmPassword(v) { this.setField("_confirmPassword", v); }
  get error() { return this._error; }
  set error(v) { this.setField("_error", v); }
  get status() { return this._status; }
  get notBusy() { return !this._busy; }
  onEnter() { this.submit(); }
  goLogin() { WindowNavigator.show("tpl-login", new LoginViewModel()); }
  async submit() {
    this.error = "";
    this.setField("_busy", true);
    try {
      const res = await api("register", {
        fullName: this.fullName, login: this.login, password: this.password, confirmPassword: this.confirmPassword,
      });
      if (!res.ok) { this.error = res.message; return; }
      await MessageBox.info(res.message, "Реєстрація");
      const next = new LoginViewModel();
      next._login = this.login;
      WindowNavigator.show("tpl-login", next);
    } finally { this.setField("_busy", false); }
  }
}

/* ---------------- Головне вікно: пошук рейсів ---------------- */
class MainViewModel extends BindableBase {
  constructor(login, fullName) {
    super();
    this._login = login; this._fullName = fullName || "";
    this._mode = "name"; this._query = ""; this._dateQuery = new Date().toLocaleDateString("uk-UA");
    this._trips = []; this._selected = null; this._status = ""; this._busy = false; this._searched = false;
  }
  get userName() { return this._fullName ? this._fullName + " (" + this._login + ")" : this._login; }
  get mode() { return this._mode; }
  set mode(v) { this.setField("_mode", v); }
  get isNameMode() { return this._mode === "name"; }
  get isDateMode() { return this._mode === "date"; }
  get query() { return this._query; }
  set query(v) { this.setField("_query", v); }
  get dateQuery() { return this._dateQuery; }
  set dateQuery(v) { this.setField("_dateQuery", v); }
  get trips() { return this._trips; }
  set trips(v) { this._trips = v; this.notify("trips"); this.notify("*"); }
  get selected() { return this._selected; }
  set selected(v) { this._selected = v; this.notify("trips"); this.notify("*"); }
  get hasSelection() { return !!this._selected && !this._selected.isDeparted; }
  get isEmpty() { return this._searched && this._trips.length === 0; }
  get emptyText() { return "Рейсів за вашим запитом не знайдено."; }
  get status() { return this._status; }
  set status(v) { this.setField("_status", v); }
  get notBusy() { return !this._busy; }

  loaded() { this.search(); }
  onEnter() { this.search(); }

  async search() {
    this.setField("_busy", true);
    try {
      const query = this.isDateMode ? this.dateQuery : this.query;
      const res = await api("search", { mode: this.mode, query });
      if (!res.ok) {
        if (await handleFailure(res)) return;
        await MessageBox.error(res.message, "Помилка пошуку");
        return;
      }
      this._searched = true;
      this._selected = null;
      this.trips = res.data.trips;
      this.status = res.message;
    } finally { this.setField("_busy", false); }
  }

  render_trips(tbody, trips) {
    tbody.innerHTML = "";
    trips.forEach(t => {
      const tr = document.createElement("tr");
      if (t.isDeparted) tr.classList.add("muted");
      if (this._selected && this._selected.id === t.id) tr.classList.add("selected");
      tr.append(td(t.id), td(t.name), td(t.departureAt), td(t.arrivalAt), td(t.trainName + " № " + t.trainNumber),
        td(t.isDeparted ? "відправився" : t.freeSeatsCount + " / " + t.seatsTotal, "num"), td(money(t.price), "num"));
      const r = td(stars(t.averageRating) + (t.ratingsCount ? " (" + t.averageRating + ")" : ""), "stars-text");
      tr.append(r);
      tr.addEventListener("click", () => { this.selected = t; });
      tr.addEventListener("dblclick", () => { this.selected = t; this.openSeats(); });
      tbody.appendChild(tr);
    });
  }

  async openSeats() {
    if (!this._selected) return;
    if (this._selected.isDeparted) { await MessageBox.error("Рейс уже відправився — квиток придбати не можна."); return; }
    const changed = await WindowNavigator.dialog("tpl-seats", new SeatsViewModel(this._selected));
    if (changed) this.search();
  }
  async openTickets() {
    await WindowNavigator.dialog("tpl-tickets", new TicketsViewModel());
    this.search();
  }
  async openRating() { await WindowNavigator.dialog("tpl-rating", new TrainRatingViewModel()); }
  async logout() {
    if (!(await MessageBox.confirm("Вийти з облікового запису?"))) return;
    await api("logout");
    WindowNavigator.show("tpl-login", new LoginViewModel());
  }
}

/* ---------------- Діалог вибору місця ---------------- */
class SeatsViewModel extends BindableBase {
  constructor(trip) {
    super();
    this._trip = trip; this._seat = null; this._error = ""; this._busy = false; this._changed = false;
  }
  get trip() { return this._trip; }
  set trip(v) { this._trip = v; this.notify("seats"); this.notify("*"); }
  get seats() { return this._trip.seatsTotal; }
  get seat() { return this._seat; }
  set seat(v) { this._seat = v; this.notify("seats"); this.notify("*"); }
  get error() { return this._error; }
  set error(v) { this.setField("_error", v); }
  get routeText() { return this._trip.name; }
  get metaText() {
    const t = this._trip;
    return "Рейс №" + t.id + " · " + t.trainName + " № " + t.trainNumber + " · відправлення " + t.departureAt +
      " · прибуття " + t.arrivalAt + " · вільно " + t.freeSeatsCount + " з " + t.seatsTotal;
  }
  get seatText() { return this._seat ? "№ " + this._seat : "не обрано"; }
  get priceText() { return this._seat ? money(this._trip.price) + " грн" : "—"; }
  get canOrder() { return !!this._seat && !this._busy; }

  render_seats(grid) {
    grid.innerHTML = "";
    const taken = new Set(this._trip.takenSeats);
    // місця у вагоні: 2 ряди зверху, прохід, 2 ряди знизу
    for (let n = 1; n <= this._trip.seatsTotal; n++) {
      const b = document.createElement("button");
      b.className = "seat";
      b.textContent = n;
      const col = Math.floor((n - 1) / 4) + 1, pos = (n - 1) % 4;
      b.style.gridColumn = col;
      b.style.gridRow = [1, 2, 4, 5][pos];
      if (taken.has(n)) { b.classList.add("taken"); b.disabled = true; b.title = "Місце зайняте"; }
      if (n === this._seat) b.classList.add("selected");
      b.addEventListener("click", () => { this.error = ""; this.seat = this._seat === n ? null : n; });
      grid.appendChild(b);
    }
  }
  async reload() {
    const res = await api("trip", { tripId: this._trip.id });
    if (res.ok) this.trip = res.data.trip;
  }
  book() { this.order("book"); }
  buy() { this.order("buy"); }
  async order(action) {
    this.error = "";
    this.setField("_busy", true);
    try {
      const res = await api("order", { tripId: this._trip.id, seatNumber: this._seat, action });
      if (!res.ok) {
        if (await handleFailure(res)) return;
        this.error = res.message;
        if (res.code === "CONFLICT") { this._seat = null; await this.reload(); }
        return;
      }
      this._changed = true;
      const k = res.data.ticket;
      await MessageBox.info(res.message + "\n\nКвиток №" + k.id + " · " + k.tripName + " · " + k.departureAt +
        " · місце " + k.seatNumber + " · " + money(k.price) + " грн", action === "buy" ? "Квиток куплено" : "Місце заброньовано");
      this._seat = null;
      await this.reload();
    } finally { this.setField("_busy", false); }
  }
  close() { this.closeDialog(this._changed); }
}

/* ---------------- Діалог «Мої квитки» ---------------- */
const BADGE = { "Оплачено": "badge-paid", "Заброньовано": "badge-booked", "Скасовано": "badge-cancelled", "Бронь минула": "badge-expired" };

class TicketsViewModel extends BindableBase {
  constructor() { super(); this._tickets = []; this._selected = null; this._status = ""; this._loaded = false; }
  get tickets() { return this._tickets; }
  set tickets(v) { this._tickets = v; this.notify("tickets"); this.notify("*"); }
  get selected() { return this._selected; }
  set selected(v) { this._selected = v; this.notify("tickets"); this.notify("*"); }
  get isEmpty() { return this._loaded && this._tickets.length === 0; }
  get canPay() { return !!this._selected && this._selected.canPay; }
  get canCancel() { return !!this._selected && this._selected.canCancel; }
  get canRate() { return !!this._selected && this._selected.canRate; }
  get selectedText() {
    const k = this._selected;
    if (!k) return "Оберіть квиток у таблиці";
    if (k.status === "Заброньовано") return "Бронь діє до " + k.reservedUntil;
    return "Квиток №" + k.id + " · " + k.trainName + " № " + k.trainNumber;
  }
  get status() { return this._status; }
  set status(v) { this.setField("_status", v); }

  async loaded() {
    const res = await api("mytickets");
    if (!res.ok) { if (!(await handleFailure(res))) await MessageBox.error(res.message); this.closeDialog(); return; }
    this._loaded = true;
    const id = this._selected && this._selected.id;
    this._selected = res.data.tickets.find(k => k.id === id) || null;
    this.tickets = res.data.tickets;
    if (!this._status) this.status = res.message;
  }
  render_tickets(tbody, tickets) {
    tbody.innerHTML = "";
    tickets.forEach(k => {
      const tr = document.createElement("tr");
      if (this._selected && this._selected.id === k.id) tr.classList.add("selected");
      const badge = document.createElement("span");
      badge.className = "badge " + (BADGE[k.status] || "");
      badge.textContent = k.status;
      const st = td(""); st.appendChild(badge);
      tr.append(td(k.id), td(k.tripName), td(k.departureAt), td(k.seatNumber, "num"), td(money(k.price), "num"), st,
        td(k.myRating ? stars(k.myRating) : "—", "stars-text"));
      tr.addEventListener("click", () => { this.selected = k; });
      tbody.appendChild(tr);
    });
  }
  async pay() {
    const k = this._selected;
    if (!(await MessageBox.confirm("Оплатити квиток №" + k.id + " (" + k.tripName + ", місце " + k.seatNumber + ") на суму " + money(k.price) + " грн?"))) return;
    await this.run("pay", { ticketId: k.id });
  }
  async cancel() {
    const k = this._selected;
    if (!(await MessageBox.confirm("Скасувати квиток №" + k.id + " (" + k.tripName + ", місце " + k.seatNumber + ")?"))) return;
    await this.run("cancel", { ticketId: k.id });
  }
  async rate() {
    const done = await WindowNavigator.dialog("tpl-rate", new RateViewModel(this._selected));
    if (done) { this.status = done; await this.loaded(); }
  }
  async run(action, body) {
    const res = await api(action, body);
    if (!res.ok) { if (!(await handleFailure(res))) await MessageBox.error(res.message); return; }
    this.status = res.message;
    await this.loaded();
  }
  close() { this.closeDialog(); }
}

/* ---------------- Діалог оцінки рейсу ---------------- */
class RateViewModel extends BindableBase {
  constructor(ticket) { super(); this._ticket = ticket; this._stars = 0; this._comment = ""; this._error = ""; }
  get tripName() { return this._ticket.tripName + " · " + this._ticket.departureAt; }
  get stars() { return this._stars; }
  set stars(v) { this._stars = v; this.notify("stars"); this.notify("*"); }
  get comment() { return this._comment; }
  set comment(v) { this.setField("_comment", v); }
  get error() { return this._error; }
  set error(v) { this.setField("_error", v); }
  render_stars(el) {
    el.innerHTML = "";
    for (let i = 1; i <= 5; i++) {
      const b = document.createElement("button");
      b.className = "star" + (i <= this._stars ? " on" : "");
      b.textContent = "★";
      b.title = i + " з 5";
      b.addEventListener("click", () => { this.error = ""; this.stars = i; });
      el.appendChild(b);
    }
  }
  async submit() {
    const res = await api("rate", { tripId: this._ticket.tripId, stars: this._stars, comment: this._comment });
    if (!res.ok) { if (!(await handleFailure(res))) this.error = res.message; return; }
    this.closeDialog(res.message + " Середня оцінка рейсу: " + res.data.averageRating + " (" + res.data.ratingsCount + " оцінок).");
  }
  close() { this.closeDialog(null); }
}

/* ---------------- Діалог рейтингу поїздів ---------------- */
class TrainRatingViewModel extends BindableBase {
  constructor() { super(); this._trains = []; this._ascending = false; }
  get trains() { return this._trains; }
  set trains(v) { this._trains = v; this.notify("trains"); this.notify("*"); }
  get sortText() { return this._ascending ? "Сортувати: кращі зверху" : "Сортувати: гірші зверху"; }
  async loaded() {
    const res = await api("trainrating");
    if (!res.ok) { if (!(await handleFailure(res))) await MessageBox.error(res.message); this.closeDialog(); return; }
    this.trains = res.data.trains;
  }
  toggleSort() {
    this._ascending = !this._ascending;
    this.trains = [...this._trains].sort((a, b) => this._ascending ? b.place - a.place : a.place - b.place);
  }
  render_trains(tbody, trains) {
    tbody.innerHTML = "";
    trains.forEach(t => {
      const tr = document.createElement("tr");
      tr.append(td(t.place, "num"), td(t.name), td(t.number),
        td(t.ratingsCount ? stars(t.averageRating) + "  " + t.averageRating.toFixed(2) : "немає оцінок", "stars-text"),
        td(t.ratingsCount, "num"));
      tbody.appendChild(tr);
    });
  }
  close() { this.closeDialog(); }
}

/* ---------------- Старт ---------------- */
window.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await api("session");
    if (res.ok && res.data.loggedIn) WindowNavigator.show("tpl-main", new MainViewModel(res.data.login, res.data.fullName));
    else WindowNavigator.show("tpl-login", new LoginViewModel());
  } catch (e) {
    document.getElementById("desktop").textContent = "Помилка запуску інтерфейсу: " + e.message;
  }
});
