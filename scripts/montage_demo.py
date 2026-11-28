"""
File:   montage_demo.py
Brief:  Монтаж демо-ролика «Цифровой механик» из demo/raw + demo/timeline.json.
Author: Nate (ZCode)
Date:   2026-11-28
Version: v0.1.0

Конвейер:
1. Титульная и финальная карточки: HTML -> PNG скриншотом через Playwright
   (кректная кириллица без борьбы с drawtext/libass-шрифтами).
2. Блоки нарезки: границы по меткам из timeline.json, у каждого блока свой
   множитель скорости (ожидание LLM ускоряется, взаимодействия — нет).
3. Нормализация сегментов (30 fps, 1600x900, yuv420p, H.264), мобильный
   дубль — pillarbox на тёмном фоне.
4. Concat + прожиг ASS-субтитров (реплики из timeline.json + врезки плана
   на время ожидания агента).

Запуск:
    .venv/Scripts/python.exe scripts/montage_demo.py
    (ffmpeg должен быть на PATH; требует playwright из .venv)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "demo"
RAW = DEMO / "raw"
TIMELINE_PATH = DEMO / "timeline.json"
FONTS_DIR = "C:/Windows/Fonts"

W, H = 1600, 900
FPS = 30
CRF = 19
TITLE_S = 7.0
FINAL_S = 9.0

# Целевая видимая длительность ожидания LLM (с) и потолок ускорения:
WAIT_TARGET = 9.0
SPEED_CAP = 4.0


# ---------------------------------------------------------------------------
# Карточки (title / final) — HTML в Chromium
# ---------------------------------------------------------------------------

CARD_CSS = """
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { width:1600px; height:900px; background:#11141c; color:#e8ecf4;
         font-family:'Segoe UI', Arial, sans-serif; display:flex;
         flex-direction:column; justify-content:center; align-items:center;
         text-align:center; }
  .kicker { font-size:26px; color:#8fa3c8; letter-spacing:2px; margin-bottom:28px; }
  h1 { font-size:92px; font-weight:700; margin-bottom:24px; }
  h1 .accent { color:#5aa2ff; }
  .mid { font-size:34px; color:#c6d2e6; line-height:1.5; max-width:1240px; }
  .bullets { font-size:30px; color:#c6d2e6; line-height:1.9; text-align:left; margin-top:8px; }
  .bullets b { color:#5aa2ff; font-weight:600; }
  .foot { position:absolute; bottom:44px; left:0; right:0; font-size:22px; color:#6b7a99; }
  .badge { display:inline-block; background:#1c2233; border:1px solid #2c3852;
           color:#9fb4dd; border-radius:999px; padding:10px 26px; font-size:26px; }
</style>
"""

TITLE_HTML = CARD_CSS + """
<body>
  <div class="kicker">Хакатон «ИИкузница» · трек «НейроДВС»</div>
  <h1>Цифровой <span class="accent">механик</span></h1>
  <div class="mid">AI-агент диагностики ДВС:<br>
    Mock ML → ответ строго по заводским руководствам (RAG, со страницами) → заявка в ТОиР</div>
  <div class="foot">Демонстрация сценариев С1–С3 · без звука · 3 мин</div>
</body>
"""

FINAL_HTML = CARD_CSS + """
<body>
  <h1>Цифровой <span class="accent">механик</span></h1>
  <div class="bullets">
    • Сценарии <b>С1–С3</b>: отклонение, честный отказ, сбой записи — без падений<br>
    • Нормативы и процедуры — <b>только из руководства на двигатель этой машины</b>, со страницей<br>
    • Инструменты агента раздельны: ML · RAG · ТОиР — выбор по контексту<br>
    • Гибридный RAG (BM25 + bge-m3) · локальная LLM · адаптив с телефона<br>
    • Экономика: <b>≈0,83 ₽</b> за сценарий · <b>≈89 ₽/мес</b> на парк 50 ТС
  </div>
  <div class="foot">Код и инструкция запуска — в репозитории команды (README, запуск за 5 минут)</div>
</body>
"""


def render_cards() -> None:
    import sys

    from playwright.sync_api import sync_playwright

    sys.path.insert(0, str(REPO))
    from scripts.record_demo import launch_browser  # noqa: E402

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        page = browser.new_context(viewport={"width": W, "height": H}).new_page()
        for name, html in (("card_title", TITLE_HTML), ("card_final", FINAL_HTML)):
            page.set_content(html)
            page.screenshot(path=str(DEMO / f"{name}.png"))
            print(f"[card] {name}.png")
        browser.close()


# ---------------------------------------------------------------------------
# План нарезки: (start_mark, end_mark, speed_rule)
# speed_rule: float | "wait:N" (цель WAIT_TARGET, потолок SPEED_CAP)
# ---------------------------------------------------------------------------

DESK_BLOCKS: list[tuple[str, str, object]] = [
    ("@start", "login_done", 1.1),
    ("login_done", "park_grid", 1.0),
    ("park_grid", "chat_open", 1.0),
    ("chat_open", "diag_send", 1.0),
    ("diag_send", "diag_done", ("wait", 3.0)),
    ("diag_done", "rag_send", 1.0),
    ("rag_send", "rag_done", ("wait", 4.5)),
    ("rag_done", "doc_open", 1.0),
    ("doc_open", "ticket_send", 1.0),
    ("ticket_send", "ticket_modal", ("wait", 4.0)),
    ("ticket_modal", "ticket_done", 1.0),
    ("ticket_done", "new_dialog", 1.0),
    ("new_dialog", "c2_send", 1.0),
    ("c2_send", "c2_done", ("wait", 5.0)),
    ("c2_done", "c3_send", 1.0),
    ("c3_send", "c3_done", ("wait", 3.0)),
    ("c3_done", "@end", 1.0),
]

# Мобильный дубль: до чата целиком, ожидание вердикта — ускоренно.
MOBILE_BLOCKS: list[tuple[str, str, object]] = [
    ("@start", "m_chat", 1.0),
    ("m_chat", "m_diag_done", "wait"),
    ("m_diag_done", "@end", 1.0),
]

# Врезки-субтитры на время ожидания агента: (mark_start, доля блока, текст)
EXTRA_CUES: list[tuple[str, float, str]] = [
    ("diag_send", 0.45, "Агент сам выбирает инструменты: ML-диагностика → память ТС → ответ"),
    ("rag_send", 0.45, "Гибридный RAG по руководствам на ЯМЗ-536: РК и РЭ"),
    ("ticket_send", 0.45, "Агент собирает заявку: работы, запчасти и источники — из базы знаний"),
    ("c2_send", 0.5, "Ответ — только по документам, с указанием страницы"),
    ("c3_send", 0.5, "Запись непригодна — диагноз не ставится"),
]


# Метки моментов отправки: рекордер ставит их с недавней версии; для старых
# записей границы восстанавливаются по старту реплики субтитра (sub() стоит
# прямо перед отправкой).
SEND_FROM_CUE: dict[str, str] = {
    "diag_send": "Механик запрашивает",
    "rag_send": "Вопрос механику по руководству",
    "ticket_send": "«Создай заявку»",
    "c2_send": "С2: «Можно ли",
    "c3_send": "С3: проверка вернула",
}


def normalize_marks(entry: dict) -> dict[str, float]:
    """Дополнить marks границами отправки, восстановленными из реплик.

    Если реплика-ориентир не найдена (например, в мобильной сцене таких
    меток нет) — просто пропускаем: блоки нарезки используют только те
    метки, которые им нужны.
    """
    marks = {k: float(v) for k, v in entry["marks"].items()}
    for name, prefix in SEND_FROM_CUE.items():
        if name in marks:
            continue
        for cue in entry["cues"]:
            if cue[2].startswith(prefix):
                marks[name] = float(cue[0])
                break
    return marks


def _resolve(mark: str, marks: dict[str, float], duration: float) -> float:
    if mark == "@start":
        return 0.0
    if mark == "@end":
        return duration
    return marks[mark]


def _speed(rule: object, in_dur: float) -> float:
    if isinstance(rule, (int, float)):
        return float(rule)
    if isinstance(rule, tuple):  # ("wait", cap)
        return float(min(rule[1], max(1.0, in_dur / WAIT_TARGET)))
    return float(min(SPEED_CAP, max(1.0, in_dur / WAIT_TARGET)))


def build_segments(tl: dict) -> list[Path]:
    """Нарезка + ускорение: возвращает список путей сегментов по порядку."""
    segs: list[Path] = []
    desk, mobile = tl["desk"], tl["mobile"]
    plans: list[tuple[str, Path, dict]] = [
        ("desk", RAW / "desk.webm", desk),
        ("mobile", RAW / "mobile.webm", mobile),
    ]

    idx = 0
    for scene_name, video, entry in plans:
        marks = normalize_marks(entry)
        duration = float(entry["duration"])
        blocks = DESK_BLOCKS if scene_name == "desk" else MOBILE_BLOCKS
        for start_m, end_m, rule in blocks:
            t0 = _resolve(start_m, marks, duration)
            t1 = _resolve(end_m, marks, duration)
            in_dur = t1 - t0
            if in_dur <= 0.05:
                continue
            speed = _speed(rule, in_dur)
            out_dur = in_dur / speed
            idx += 1
            seg = DEMO / f"seg_{idx:02d}.mp4"
            if scene_name == "desk":
                vf = (
                    f"setpts=PTS/{speed:.4f},fps={FPS},"
                    f"scale={W}:{H}:flags=lanczos,format=yuv420p"
                )
            else:
                vf = (
                    f"setpts=PTS/{speed:.4f},fps={FPS},scale=-2:{H},"
                    f"pad={W}:{H}:(ow-iw)/2:0:color=0x11141c,format=yuv420p"
                )
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                # -ss/-t ДО -i: лимит длительности ВХОДА. Как выходная опция
                # -t не срабатывает для ускоренных сегментов (выход короче
                # лимита) — в блок уезжал хвост исходника до конца файла.
                "-ss", f"{t0:.3f}", "-t", f"{in_dur:.3f}", "-i", str(video),
                "-vf", vf, "-an", "-c:v", "libx264", "-crf", str(CRF),
                "-preset", "medium", str(seg),
            ]
            subprocess.run(cmd, check=True)
            print(f"[seg {idx:02d}] {scene_name} {start_m}→{end_m} "
                  f"{in_dur:6.2f}s x{speed:.2f} → {out_dur:5.2f}s")
            segs.append(seg)
    return segs


def concat(segs: list[Path]) -> Path:
    lst = DEMO / "concat.txt"
    lst.write_text(
        "\n".join(f"file '{seg.as_posix()}'" for seg in segs), encoding="utf-8"
    )
    out = DEMO / "concat.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
        check=True, cwd=DEMO,
    )
    return out


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(tl: dict) -> Path:
    """ASS из реплик timeline.json (маппинг реального времени в финальное)."""
    desk, mobile = tl["desk"], tl["mobile"]
    events: list[tuple[float, float, str]] = []

    plans = [("desk", desk, DESK_BLOCKS), ("mobile", mobile, MOBILE_BLOCKS)]
    out_t = TITLE_S  # титульная карточка идёт до всех видео-блоков
    for scene_name, entry, blocks in plans:
        marks = normalize_marks(entry)
        duration = float(entry["duration"])
        cues = [list(c) for c in entry["cues"]]  # [t0, t1, text]
        for start_m, end_m, rule in blocks:
            t0 = _resolve(start_m, marks, duration)
            t1 = _resolve(end_m, marks, duration)
            in_dur = t1 - t0
            if in_dur <= 0.05:
                continue
            speed = _speed(rule, in_dur)
            block_out_dur = in_dur / speed

            # реплики записи, пересекающиеся с блоком
            for cue in cues:
                c0, c1 = min(cue[0], t1), min(cue[1], t1)
                if c1 <= t0 or c0 >= t1 or c1 <= c0:
                    continue
                # если реплика началась до блока (перетекла) — визуально обрежем
                e0 = out_t + max(0.0, (c0 - t0)) / speed
                e1 = out_t + (c1 - t0) / speed
                events.append((e0, e1, cue[2]))
            # врезки плана внутри блока
            for m_start, frac, text in EXTRA_CUES:
                if m_start == start_m:
                    e0 = out_t + frac * block_out_dur
                    e1 = out_t + block_out_dur
                    events.append((e0, e1, text))

            out_t += block_out_dur

    events.sort()
    style = (
        "Style: Default,Segoe UI,38,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,"
        "0,0,0,0,100,100,0.6,0,1,2.4,1.2,2,30,30,36,1"
    )
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        style,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]
    for e0, e1, text in events:
        safe = text.replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{_ass_time(e0)},{_ass_time(e1)},Default,,0,0,0,,{safe}")
    path = DEMO / "subs.ass"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    n = len(events)
    print(f"[ass] {n} реплик -> {path.name}")
    return path


def burn(concat_path: Path, ass_path: Path) -> Path:
    out = DEMO / "demo_final.mp4"
    # Шрифты кладём рядом с ass: относительный fontsdir без двоеточий —
    # ffmpeg-парсер фильтров не любит Windows-пути с ':' без многослойного
    # экранирования.
    fonts = DEMO / "fonts"
    fonts.mkdir(exist_ok=True)
    for fname in ("segoeui.ttf", "segoeuib.ttf", "segoeuisl.ttf"):
        src = Path(FONTS_DIR) / fname
        if src.exists() and not (fonts / fname).exists():
            (fonts / fname).write_bytes(src.read_bytes())
    ass_arg = f"ass={ass_path.name}:fontsdir=fonts"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(concat_path), "-vf", ass_arg,
         "-c:v", "libx264", "-crf", str(CRF), "-preset", "medium",
         "-movflags", "+faststart", "-an", str(out)],
        check=True, cwd=DEMO,
    )
    return out


def add_cards_to_head_tail(head: Path, tail: Path) -> list[Path]:
    """Сегменты-карточки (PNG -> video) в начало и конец."""
    segs: list[Path] = []
    for name, png, dur in (("seg_00_title", "card_title.png", TITLE_S),
                           ("seg_99_final", "card_final.png", FINAL_S)):
        seg = DEMO / f"{name}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-loop", "1", "-t", str(dur), "-i", str(DEMO / png),
             "-vf", f"fps={FPS},format=yuv420p", "-an",
             "-c:v", "libx264", "-crf", str(CRF), "-preset", "medium", str(seg)],
            check=True,
        )
        segs.append(seg)
    return segs


def main() -> None:
    t0 = time.monotonic()
    tl = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))

    render_cards()
    card_segs = add_cards_to_head_tail(DEMO / "card_title.png", DEMO / "card_final.png")
    video_segs = build_segments(tl)
    all_segs = [card_segs[0]] + video_segs + [card_segs[1]]

    concat_path = concat(all_segs)
    ass_path = build_ass(tl)
    final = burn(concat_path, ass_path)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(final)],
        capture_output=True, text=True, check=True,
    )
    dur = float(probe.stdout.strip())
    print(f"[final] {final.name}: {dur:.1f}s ({int(dur // 60)}:{int(dur % 60):02d}), "
          f"всего {time.monotonic() - t0:.0f}s монтажа")
    if dur > 180.0:
        print("[warn] длительность превышает 3 минуты — увеличьте WAIT_TARGET/скорости")
        sys.exit(2)


if __name__ == "__main__":
    main()
