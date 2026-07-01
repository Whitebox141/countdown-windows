#!/usr/bin/env python3
"""
countdown.py - Temporizador de cuenta regresiva para la terminal (CMD / PowerShell de Windows)
Inspirado en https://github.com/antonmedv/countdown

Uso:
    python countdown.py 25s
    python countdown.py 11:32
    python countdown.py 1m30s && echo Listo
    python countdown.py -up 30s
    python countdown.py -say 10s 1m
    python countdown.py -title "Pomodoro" 25m

Teclas:
    Espacio       Pausar / reanudar
    Esc o Ctrl+C  Detener (no ejecuta el comando encadenado con &&)
"""

import sys
import os
import re
import time
import ctypes
import argparse
import subprocess
from datetime import datetime, timedelta

# ----------------------------------------------------------------------
# Habilitar secuencias ANSI en la consola de Windows (CMD / PowerShell)
# ----------------------------------------------------------------------
def enable_vt_mode():
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(h, ctypes.byref(mode))
        kernel32.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
DIM = "\x1b[2m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_HOME = "\x1b[2J\x1b[H"


# ----------------------------------------------------------------------
# Fuente "gigante" tipo LED, 5 filas por carácter
# ----------------------------------------------------------------------
FONT = {
    "0": ["█████", "█   █", "█   █", "█   █", "█████"],
    "1": ["   █ ", "   █ ", "   █ ", "   █ ", "   █ "],
    "2": ["█████", "    █", "█████", "█    ", "█████"],
    "3": ["█████", "    █", "█████", "    █", "█████"],
    "4": ["█   █", "█   █", "█████", "    █", "    █"],
    "5": ["█████", "█    ", "█████", "    █", "█████"],
    "6": ["█████", "█    ", "█████", "█   █", "█████"],
    "7": ["█████", "    █", "    █", "    █", "    █"],
    "8": ["█████", "█   █", "█████", "█   █", "█████"],
    "9": ["█████", "█   █", "█████", "    █", "█████"],
    ":": ["   ", " █ ", "   ", " █ ", "   "],
    " ": ["  ", "  ", "  ", "  ", "  "],
    "-": ["     ", "     ", "█████", "     ", "     "],
}


def render_big_text(text):
    rows = ["", "", "", "", ""]
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        for i in range(5):
            rows[i] += glyph[i] + " "
    return rows


# ----------------------------------------------------------------------
# Parseo de duración estilo Go: 1h2m3s, 90s, 1m30s, etc.
# ----------------------------------------------------------------------
DURATION_RE = re.compile(
    r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
)


def parse_duration(s):
    m = DURATION_RE.match(s.strip())
    if not m or not any(m.groups()):
        return None
    h, mi, se = (int(g) if g else 0 for g in m.groups())
    return timedelta(hours=h, minutes=mi, seconds=se)


def parse_target_time(s):
    s = s.strip()
    now = datetime.now()
    fmts = ["%H:%M", "%I:%M%p", "%I:%M %p"]
    for fmt in fmts:
        try:
            t = datetime.strptime(s.upper(), fmt.upper() if "%p" in fmt else fmt)
        except ValueError:
            continue
        target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target
    return None


def fmt_remaining(td):
    total = int(td.total_seconds())
    if total < 0:
        total = 0
    h, rem = divmod(total, 3600)
    mi, se = divmod(rem, 60)
    if h > 0:
        return f"{h}:{mi:02d}:{se:02d}"
    return f"{mi:02d}:{se:02d}"


# ----------------------------------------------------------------------
# Voz (equivalente Windows del "say" de macOS), usando System.Speech via PowerShell
# ----------------------------------------------------------------------
def speak(text):
    try:
        ps_cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('"
            + text.replace("'", "''") + "')"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ----------------------------------------------------------------------
# Lectura de teclas no bloqueante (Windows)
# ----------------------------------------------------------------------
def get_key():
    if os.name != "nt":
        return None
    import msvcrt
    if msvcrt.kbhit():
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            msvcrt.getch()  # descartar segundo byte de teclas especiales
            return None
        if ch == b"\x1b":
            return "ESC"
        if ch == b" ":
            return "SPACE"
        if ch == b"\x03":
            return "CTRLC"
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Temporizador de cuenta regresiva para CMD / PowerShell de Windows."
    )
    parser.add_argument("when", help="Duración (25s, 1m30s, 1h2m3s) u hora objetivo (14:15, 02:15pm)")
    parser.add_argument("-up", dest="count_up", action="store_true", help="Cuenta hacia arriba desde cero")
    parser.add_argument("-say", dest="say", default=None, help="Anunciar en voz alta los últimos N segundos (p. ej. -say 10s)")
    parser.add_argument("-title", dest="title", default=None, help="Título a mostrar bajo el temporizador")
    args = parser.parse_args()

    duration = parse_duration(args.when)
    target_time = None
    if duration is None:
        target_time = parse_target_time(args.when)
        if target_time is None:
            print(f"No se pudo interpretar '{args.when}'. Usa algo como 25s, 1m30s, 1h2m3s o 14:15.")
            sys.exit(2)
        duration = target_time - datetime.now()

    say_seconds = 0
    if args.say:
        say_td = parse_duration(args.say)
        if say_td is None:
            print(f"No se pudo interpretar -say '{args.say}'.")
            sys.exit(2)
        say_seconds = int(say_td.total_seconds())

    if os.name != "nt":
        print("Este script está pensado para Windows (CMD / PowerShell).")

    enable_vt_mode()
    total = duration
    end_time = datetime.now() + duration
    paused = False
    frozen_remaining = None  # tiempo restante congelado mientras está en pausa
    last_announced = None
    last_drawn_key = None  # para redibujar solo cuando algo realmente cambió

    def draw(remaining, paused_flag):
        display_value = (total - remaining) if args.count_up else remaining
        print(CLEAR_HOME, end="")
        rows = render_big_text(fmt_remaining(display_value))
        for r in rows:
            print(CYAN + BOLD + r + RESET)
        if args.title:
            print()
            print(DIM + args.title + RESET)
        print()
        if paused_flag:
            print(DIM + "PAUSADO   [Espacio] reanudar   [Esc] detener" + RESET)
        else:
            print(DIM + "[Espacio] pausar/reanudar   [Esc] detener" + RESET)

    print(HIDE_CURSOR, end="")
    try:
        while True:
            key = get_key()
            if key in ("ESC", "CTRLC"):
                raise KeyboardInterrupt
            if key == "SPACE":
                if not paused:
                    paused = True
                    frozen_remaining = end_time - datetime.now()
                else:
                    paused = False
                    end_time = datetime.now() + frozen_remaining
                    frozen_remaining = None
                last_drawn_key = None  # forzar redibujo inmediato

            if paused:
                remaining = frozen_remaining
            else:
                remaining = end_time - datetime.now()

            remaining_secs = remaining.total_seconds()

            if not paused and remaining_secs <= 0:
                remaining = timedelta(seconds=0)
                draw(remaining, paused)
                break

            # Redibujar solo cuando cambia el segundo mostrado o el estado de pausa
            draw_key = (int(remaining_secs), paused)
            if draw_key != last_drawn_key:
                draw(remaining, paused)
                last_drawn_key = draw_key

            if not paused and say_seconds > 0:
                secs_left = int(round(remaining_secs))
                if 0 < secs_left <= say_seconds and secs_left != last_announced:
                    speak(str(secs_left))
                    last_announced = secs_left

            time.sleep(0.05)

    except KeyboardInterrupt:
        print(SHOW_CURSOR, end="")
        print("\nCancelado.")
        sys.exit(1)

    print(SHOW_CURSOR, end="")
    sys.exit(0)


if __name__ == "__main__":
    main()
