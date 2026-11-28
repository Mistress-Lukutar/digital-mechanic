"""
File:   record_demo.py
Brief:  Автоматическая запись демо-ролика «Цифровой механик» (Playwright).
Author: Nate (ZCode)
Date:   2026-11-28
Version: v0.1.0

Сценарий хакатона «ИИкузница»: С1 (отклонение F08 -> RAG -> заявка),
С2 (перегон своим ходом), С3 (сбой записи). Пишет видео посегментно
через Playwright record_video_dir: один непрерывный десктопный дубль
(login -> парк -> чат -> диагностика -> RAG -> DocPanel -> заявка -> C2 -> C3)
и отдельный мобильный контекст (390x844).

Выход:
- demo/raw/desk.webm, demo/raw/mobile.webm
- demo/timeline.json: длительности, метки (marks) и реплики субтитров
  (cues) с реальными таймингами — их читает demo/montage.py.

Режим --rehearse: тот же сценарий без записи, с укороченными паузами,
печатает фактические длительности шагов (тайминги LLM).

Запуск:
    .venv/Scripts/python.exe scripts/record_demo.py [--rehearse]
    DEMO_BASE_URL=http://127.0.0.1:8011/ DEMO_USER=demo_mech
    DEMO_PASS=demo-mech-2026 DEMO_VEHICLE=C935KO47 DEMO_GARAGE=Г-124
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "demo" / "raw"
TIMELINE_PATH = REPO / "demo" / "timeline.json"

BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8011/")
DEMO_USER = os.environ.get("DEMO_USER", "demo_mech")
DEMO_PASS = os.environ.get("DEMO_PASS", "demo-mech-2026")

# История ТС Г-124: S-0090/S-0091 = F08 аномалия, S-0092 = check_failed.
VEHICLE = os.environ.get("DEMO_VEHICLE", "C935KO47")
GARAGE = os.environ.get("DEMO_GARAGE", "Г-124")
SESSION_ANOM = os.environ.get("DEMO_SESSION", "S-0091")
SESSION_FAIL = os.environ.get("DEMO_SESSION_FAIL", "S-0092")

DESKTOP_VP = {"width": 1600, "height": 900}
DESKTOP_REC = {"width": 1600, "height": 900}
MOBILE_VP = {"width": 390, "height": 844}
# ВАЖНО: при is_mobile размер видео должен совпадать с viewport (CSS-px).
# record_video_size > viewport ломает screencast: страница уезжает в угол
# кадра, остальное — серый фон (проверено на chromium 1255).
MOBILE_REC = {"width": 390, "height": 844}

# Реплики механика (то, что «печатает» демо-пользователь).
M_DIAG = f"Получи результат проверки {SESSION_ANOM} по этой машине"
M_RAG = "Чем это опасно? По какой процедуре проверить топливоподачу по руководству?"
M_TICKET = f"Создай заявку на дефектовку по проверке {SESSION_ANOM}"
M_MOVE = "Можно ли своим ходом перегнать машину на базу?"
M_FAIL = f"Получи результат проверки {SESSION_FAIL}"

# ---------------------------------------------------------------------------
# Fake cursor: DOM-стрелка + пульс клика (видимые «руки механика» в кадре).
# ---------------------------------------------------------------------------

CURSOR_JS = """
(() => {
  if (document.getElementById('demo-cursor')) return;
  const cur = document.createElement('div');
  cur.id = 'demo-cursor';
  cur.style.cssText = 'position:fixed;left:0;top:0;width:24px;height:24px;' +
    'z-index:2147483647;pointer-events:none;' +
    'transition:transform .3s cubic-bezier(.3,.7,.4,1);' +
    'filter:drop-shadow(0 1px 3px rgba(0,0,0,.55));';
  cur.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24">' +
    '<path d="M4 2l16 8.6-7.2 1.5-2.9 6.7z" fill="#fff" stroke="#111" stroke-width="1.4"/></svg>';
  document.body.appendChild(cur);
  window.__demoMove = (x, y) => { cur.style.transform = 'translate(' + (x - 5) + 'px,' + (y - 4) + 'px)'; };
  window.__demoPulse = (x, y) => {
    const p = document.createElement('div');
    p.style.cssText = 'position:fixed;left:' + (x - 17) + 'px;top:' + (y - 17) + 'px;' +
      'width:34px;height:34px;border:3px solid rgba(80,160,255,.95);border-radius:50%;' +
      'pointer-events:none;z-index:2147483646;animation:demoPulse .55s ease-out forwards;';
    document.body.appendChild(p);
    setTimeout(() => p.remove(), 650);
  };
  const st = document.createElement('style');
  st.textContent = '@keyframes demoPulse{0%{transform:scale(.35);opacity:1}' +
    '100%{transform:scale(1.7);opacity:0}}';
  document.body.appendChild(st);
})();
"""

BUSY_JS = """
() => {
  const ind = document.querySelector('.streaming-indicator');
  const spin = document.querySelector('.agent-step .spinner');
  const texts = document.querySelectorAll('.assistant-bubble .message-text');
  const last = texts[texts.length - 1];
  const lastLen = last ? last.textContent.trim().length : 0;
  return {
    busy: !!ind || !!spin || lastLen < 5,
    reason: [ind ? 'streaming' : null, spin ? 'step-spinner' : null,
             lastLen < 5 ? 'no-text(len=' + lastLen + ')' : null].filter(Boolean),
    bubbles: document.querySelectorAll('.assistant-bubble').length,
    lastLen: lastLen,
  };
}
"""


# ---------------------------------------------------------------------------
# Browser launch: канал как в e2e (msedge > chrome > bundled). Установленные
# ms-playwright-браузеры могут не совпадать по версии с пакетом playwright
# в .venv — системный канал от этого не зависит.
# ---------------------------------------------------------------------------

def launch_browser(pw):
    """Запустить headless-браузер.

    По умолчанию — bundled chromium (запись видео гарантированно работает
    именно в bundled headless); DEMO_CHANNEL или msedge/chrome — фолбэк.
    """
    env_ch = os.environ.get("DEMO_CHANNEL")
    order = [env_ch] if env_ch else [None, "msedge", "chrome"]
    last_exc: Exception | None = None
    for ch in order:
        kwargs: dict = {"headless": True}
        if ch:
            kwargs["channel"] = ch
        try:
            probe = pw.chromium.launch(**kwargs)
            probe.close()
            return pw.chromium.launch(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(f"Не найден браузер для записи: {last_exc}")


# ---------------------------------------------------------------------------
# Scene runner
# ---------------------------------------------------------------------------

class Scene:
    """Один дубль = один browser context; пишет video + тайминг-метки."""

    def __init__(self, pw: sync_playwright, name: str, *, mobile: bool = False,
                 record: bool = True, hold_scale: float = 1.0) -> None:
        self.name = name
        self.record = record
        self.hold_scale = hold_scale
        self.mobile = mobile
        vdir = OUT_DIR / name
        vdir.mkdir(parents=True, exist_ok=True)

        kwargs: dict = {
            "viewport": MOBILE_VP if mobile else DESKTOP_VP,
            "device_scale_factor": 2 if mobile else 1,
            "is_mobile": mobile,
            "has_touch": mobile,
            "record_video_size": MOBILE_REC if mobile else DESKTOP_REC,
        }
        if record:
            kwargs["record_video_dir"] = str(vdir)
        self.ctx = launch_browser(pw).new_context(**kwargs)
        self.page: Page = self.ctx.new_page()
        self._cursor_ready = False
        self.page.set_default_timeout(20000)
        self.t0 = time.monotonic()
        self.cues: list[list] = []   # [t_rel, text]
        self.marks: dict[str, float] = {}
        self._open_cue: tuple[float, str] | None = None

    # --- timing -----------------------------------------------------------

    def _now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def mark(self, name: str) -> None:
        self.marks[name] = self._now()

    def sub(self, text: str) -> None:
        """Открыть субтитр; закрывается следующим sub() или финишем сцены."""
        t = self._now()
        if self._open_cue is not None:
            self.cues.append([self._open_cue[0], t, self._open_cue[1]])
        self._open_cue = (t, text)

    def hold(self, seconds: float) -> None:
        time.sleep(seconds * self.hold_scale)

    # --- mouse ------------------------------------------------------------

    def ensure_cursor(self) -> None:
        """Инжект DOM-курсора после загрузки страницы (evaluate, а не
        init-script: независимость от CSP и тайминга навигации)."""
        if self._cursor_ready or self.mobile:
            return
        self.page.evaluate(CURSOR_JS)
        self._cursor_ready = True

    def move(self, selector: str) -> None:
        self.ensure_cursor()
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        if box is None:
            return
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        if not self.mobile:
            self.page.evaluate("([x, y]) => window.__demoMove(x, y)", [x, y])
        time.sleep(0.28 + random.uniform(0.0, 0.15) * self.hold_scale)

    def click(self, selector: str) -> None:
        self.move(selector)
        if not self.mobile:
            box = self.page.locator(selector).first.bounding_box()
            if box:
                self.page.evaluate(
                    "([x, y]) => window.__demoPulse(x, y)",
                    [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
                )
        self.page.locator(selector).first.click()
        time.sleep(0.25)

    def type_text(self, selector: str, text: str, delay_ms: int = 28) -> None:
        self.move(selector)
        self.page.locator(selector).first.click()
        self.page.locator(selector).first.fill("")
        self.page.keyboard.type(text, delay=int(delay_ms * self.hold_scale))

    # --- app-specific -------------------------------------------------------

    def login(self) -> None:
        page = self.page
        page.goto(BASE_URL)
        page.wait_for_selector("#login-user", state="visible")
        self.type_text("#login-user", DEMO_USER, delay_ms=22)
        self.type_text("#login-pass", DEMO_PASS, delay_ms=18)
        self.click("#login-consent")
        self.click("button:has-text('Войти')")
        page.wait_for_selector(".vehicle-card", state="visible")
        self.hold(0.6)

    def send_message(self, text: str, composer: str = ".composer-line textarea") -> None:
        """Отправить сообщение и запомнить число ответов до отправки."""
        self._assist_before = self.page.evaluate(
            "document.querySelectorAll('.assistant-bubble').length"
        )
        self.type_text(composer, text)
        time.sleep(0.35)
        self.click(".send-btn")

    def wait_stream(self, timeout_s: float = 300.0) -> float:
        """Ждать завершения ответа на ПОСЛЕДНЕЕ сообщение; вернуть длительность (с).

        Гард от гонки: сначала появления нового assistant-бабла, потом
        конца стриминга. В конце — периодический лог причины ожидания,
        чтобы зависание диагностировалось, а не было слепым таймаутом.
        """
        t_start = time.monotonic()
        before = getattr(self, "_assist_before", None)
        if before is None:
            raise RuntimeError("wait_stream без send_message")
        deadline = t_start + timeout_s
        # 1) дождаться нового бабла ответа
        while time.monotonic() < deadline:
            n = self.page.evaluate(
                "document.querySelectorAll('.assistant-bubble').length"
            )
            if n > before:
                break
            if self.page.locator(".error-strip.chat-error").count():
                raise RuntimeError("chat error strip при ожидании ответа")
            self.page.wait_for_timeout(400)
        # 2) дождаться конца стриминга
        last_log = t_start
        while time.monotonic() < deadline:
            st = self.page.evaluate(BUSY_JS)
            if not st["busy"]:
                break
            if self.page.locator(".error-strip.chat-error").count():
                raise RuntimeError(f"chat error strip при ожидании: {st}")
            if time.monotonic() - last_log > 30:
                last_log = time.monotonic()
                print(f"[wait:{self.name}] {time.monotonic() - t_start:.0f}s "
                      f"reason={st['reason']} bubbles={st['bubbles']} "
                      f"lastLen={st['lastLen']}")
            self.page.wait_for_timeout(500)
        else:
            raise TimeoutError(f"{self.name}: ответ агента не завершён за {timeout_s}s: {st}")
        self._assist_before = None
        return round(time.monotonic() - t_start, 1)

    def close_ticket_modal(self) -> None:
        page = self.page
        if page.locator(".modal-overlay .modal-close").count():
            page.locator(".modal-overlay .modal-close").first.click()
        else:
            page.keyboard.press("Escape")
        try:
            page.wait_for_selector(".modal-overlay", state="hidden", timeout=5000)
        except Exception:
            print("[warn] ticket modal did not close")

    def wait_doc(self, timeout_s: float = 45000) -> None:
        """Дождаться рендера страницы руководства в DocPanel (canvas)."""
        self.page.wait_for_selector(
            ".chat-sidebar.right canvas", timeout=timeout_s, state="visible"
        )

    # --- finish ------------------------------------------------------------

    def finish(self) -> None:
        if self._open_cue is not None:
            self.cues.append([self._open_cue[0], self._now(), self._open_cue[1]])
            self._open_cue = None
        duration = self._now()
        self.ctx.close()
        result: dict = {
            "video": None,
            "duration": duration,
            "cues": self.cues,
            "marks": self.marks,
        }
        if self.record:
            video_path = self.page.video.path()
            target = OUT_DIR / f"{self.name}.webm"
            if target.exists():
                target.unlink()
            Path(video_path).replace(target)
            result["video"] = str(target)
        TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        timeline: dict = {}
        if TIMELINE_PATH.exists():
            timeline = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
        timeline[self.name] = result
        TIMELINE_PATH.write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[scene:{self.name}] {duration:.1f}s -> {result['video'] or '(no video)'}")
        for t0, t1, text in self.cues:
            print(f"    cue {t0:7.2f}-{t1:7.2f}  {text}")
        for name, t in self.marks.items():
            print(f"    mark {name:14s} @ {t:7.2f}")


# ---------------------------------------------------------------------------
# Десктопный дубль: login -> парк -> чат -> С1 (диагностика -> RAG -> заявка)
# -> С2 -> С3
# ---------------------------------------------------------------------------

def wipe_chats(vehicle_id: str = VEHICLE) -> int:
    """Удалить все диалоги demo-пользователя на ТС (чистое состояние)."""
    import urllib.parse
    import urllib.request

    qs = urllib.parse.urlencode({"vehicle_id": vehicle_id})
    req = urllib.request.Request(
        f"{BASE_URL}api/chats?{qs}",
        headers=_auth_headers(),
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        convs = json.loads(resp.read().decode("utf-8"))
    removed = 0
    for conv in convs:
        req = urllib.request.Request(
            f"{BASE_URL}api/chats/{conv['id']}",
            headers=_auth_headers(),
            method="DELETE",
        )
        urllib.request.urlopen(req, timeout=10)
        removed += 1
    if removed:
        print(f"[wipe] удалено диалогов demo_mech на {VEHICLE}: {removed}")
    return removed


def _auth_headers() -> dict:
    import urllib.parse
    import urllib.request

    body = json.dumps(
        {"username": DEMO_USER, "password": DEMO_PASS}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode("utf-8"))["token"]
    return {"Authorization": f"Bearer {token}"}


def wipe_tickets() -> int:
    """Удалить заявки демо-пользователя из журнала (чистая история для B1).

    Короткая транзакция в WAL — легитимно для живого сервера. Удаляются
    только строки demo-пользователя.
    """
    import sqlite3

    db = REPO / "data" / "app.db"
    con = sqlite3.connect(db, timeout=10)
    try:
        cur = con.execute(
            "DELETE FROM tickets WHERE username = ?", (DEMO_USER,)
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Десктопный дубль: login -> парк -> чат -> С1 (диагностика -> RAG -> заявка)
# -> С2 -> С3 (в новом диалоге — короткий контекст, быстрее и стабильнее)
# ---------------------------------------------------------------------------

def run_desktop(pw, *, record: bool, hold_scale: float) -> None:
    sc = Scene(pw, "desk", record=record, hold_scale=hold_scale)
    page = sc.page

    sc.sub("Механик входит в систему «Цифровой механик»")
    sc.login()
    sc.mark("login_done")

    # --- Парк: сетка ТС, группы, поиск --------------------------------------
    sc.sub("Парк автопредприятия: статус каждой машины по последней проверке")
    sc.hold(2.0)
    sc.mark("park_grid")

    sc.click(".filter-chips button:has-text('Карантин')")
    sc.hold(1.2)
    sc.sub("Группы парка: «Карантин» — машины с открытыми аномалиями (режим «Главный механик»)")
    sc.mark("park_filter")
    sc.click(".filter-chips button:has-text('Все')")
    sc.hold(0.8)

    sc.sub("Поиск машины по гаражному номеру")
    sc.type_text(".search-input", GARAGE, delay_ms=35)
    page.wait_for_selector(f".vehicle-card:has-text('{GARAGE}')", state="visible")
    sc.hold(1.0)
    sc.mark("park_search")

    sc.click(f".vehicle-card:has-text('{GARAGE}')")
    page.wait_for_selector(".chat-page", state="visible")
    sc.hold(0.8)
    sc.mark("chat_open")

    # --- Чат: история проверок (B1 + B2) ------------------------------------
    sc.sub("История проверок ТС: график anomaly_score и статусы (память по vehicle_id)")
    sc.hold(3.0)
    sc.mark("history_shown")

    # --- С1: диагностика ------------------------------------------------------
    sc.sub("Механик запрашивает результат акустической проверки")
    sc.send_message(M_DIAG)
    llm1 = sc.wait_stream()
    sc.mark("diag_done")
    print(f"[llm] diagnose turn: {llm1}s")
    sc.sub(f"Вердикт ML: неисправность F08 «Дизельная топливоподача», "
           f"оценка отклонения и уверенность на экране")
    sc.hold(7.0)

    # --- С1: RAG-ответ со ссылками -------------------------------------------
    sc.sub("Вопрос механику по руководству — ответ строго по документам этой машины")
    sc.send_message(M_RAG)
    llm2 = sc.wait_stream()
    sc.mark("rag_done")
    print(f"[llm] rag turn: {llm2}s")
    sc.sub("Ответ: гипотезы, порядок проверки и допуски — со ссылкой на страницу руководства")
    sc.hold(3.0)

    # Открыть источник из ответа (одна страница, без пролиста).
    cite = page.locator(".assistant-bubble .md-body a.citation-link").last
    if cite.count() > 0:
        sc.sub("Открываем указанный источник: страница руководства по ремонту")
        sc.click(".assistant-bubble .md-body a.citation-link >> nth=-1")
        sc.wait_doc()
        sc.mark("doc_open")
        sc.hold(6.0)
    else:
        print("[warn] citation link not found — сцена DocPanel пропущена")
        sc.mark("doc_open")

    # --- С1: заявка на дефектовку --------------------------------------------
    sc.sub("«Создай заявку» — агент собирает черновик: работы, запчасти, источники")
    sc.send_message(M_TICKET)
    page.wait_for_selector(".modal-overlay", timeout=60000)
    sc.mark("ticket_modal")
    sc.hold(2.5)
    sc.sub("Механик проверяет черновик и подаёт заявку в ТОиР")
    sc.click("button:has-text('Подать в ТОиР')")
    page.wait_for_selector(".ticket-success", timeout=30000)
    sc.mark("ticket_done")
    sc.sub("Mock-сервис ТОиР подтвердил заявку (ticket_id), источники приложены")
    sc.hold(5.0)
    sc.close_ticket_modal()
    sc.hold(0.6)

    # --- С2 + С3: в новом диалоге (короткий контекст, устойчивее и быстрее) ---
    sc.sub("Новый диалог — вопрос о перегоне своим ходом")
    sc.click(".new-dialog-btn")
    sc.hold(0.8)
    sc.mark("new_dialog")

    sc.sub("С2: «Можно ли своим ходом перегнать машину на базу?»")
    sc.send_message(M_MOVE)
    llm3 = sc.wait_stream()
    sc.mark("c2_done")
    print(f"[llm] c2 turn: {llm3}s")
    sc.sub("Ответ по базе знаний — или честное «данных недостаточно»")
    sc.hold(4.0)

    sc.sub("С3: проверка вернула «сбой записи» (плохая запись)")
    sc.send_message(M_FAIL)
    llm4 = sc.wait_stream()
    sc.mark("c3_done")
    print(f"[llm] c3 turn: {llm4}s")
    sc.sub("Агент не делает выводов о двигателе: нужно восстановить условия записи")
    sc.hold(6.0)

    sc.finish()


# ---------------------------------------------------------------------------
# Мобильный дубль: 390x844 (адаптив, UX «работает с телефона»).
# Машина Г-117 — последняя проверка F01 (аномалия): чип «Получить
# диагностику» на свежем чате даёт живой вердикт без зависимости от
# диалогов десктопной сцены.
# ---------------------------------------------------------------------------

def run_mobile(pw, *, record: bool, hold_scale: float) -> None:
    sc = Scene(pw, "mobile", mobile=True, record=record, hold_scale=hold_scale)
    page = sc.page
    garage2 = os.environ.get("DEMO_GARAGE2", "Г-117")
    wipe_chats(os.environ.get("DEMO_VEHICLE2", "O658MX98"))

    sc.sub("Тот же агент с телефона: адаптивный интерфейс")
    sc.login()
    sc.mark("m_login")

    sc.sub("Поиск машины по гаражному номеру")
    sc.type_text(".search-input", garage2, delay_ms=35)
    page.wait_for_selector(f".vehicle-card:has-text('{garage2}')", state="visible")
    sc.hold(0.8)
    sc.mark("m_search")

    sc.click(f".vehicle-card:has-text('{garage2}')")
    page.wait_for_selector(".quick-chip", state="visible")
    sc.hold(1.0)
    sc.mark("m_chat")

    sc.sub("Чип «Получить диагностику» — проверка одним касанием")
    sc._assist_before = page.evaluate(
        "document.querySelectorAll('.assistant-bubble').length"
    )
    sc.click(".quick-chip:has-text('Получить диагностику')")
    llm = sc.wait_stream()
    sc.mark("m_diag_done")
    print(f"[llm] mobile diagnose turn: {llm}s")

    sc.sub("Вердикт и цитаты руководства — на экране телефона")
    # Автоскролл чата к низу доигрывает после завершения стриминга — даём
    # ему отработать, затем дважды центрируем карточку вердикта.
    sc.hold(1.0)
    sc.page.evaluate("""() => {
      const card = document.querySelector('.status-card');
      if (card) card.scrollIntoView({block: 'center'});
    }""")
    sc.hold(0.6)
    sc.page.evaluate("""() => {
      const card = document.querySelector('.status-card');
      if (card) card.scrollIntoView({block: 'center'});
    }""")
    sc.hold(3.5)
    sc.mark("m_verdict")

    sc.sub("Вердикт, история и чат — всё под рукой")
    sc.hold(3.0)
    sc.finish()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Запись демо-ролика «Цифровой механик»")
    ap.add_argument("--rehearse", action="store_true", help="без записи видео")
    ap.add_argument("--only", default="desk,mobile", help="сцены через запятую")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    record = not args.rehearse
    hold_scale = 0.5 if args.rehearse else 1.0
    scenes = [s.strip() for s in args.only.split(",") if s.strip()]

    t0 = time.monotonic()
    with sync_playwright() as pw:
        if "desk" in scenes:
            n = wipe_tickets()
            if n:
                print(f"[wipe] удалено заявок demo_mech: {n}")
            wipe_chats()
            run_desktop(pw, record=record, hold_scale=hold_scale)
        if "mobile" in scenes:
            run_mobile(pw, record=record, hold_scale=hold_scale)
    print(f"[total] {time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    main()
