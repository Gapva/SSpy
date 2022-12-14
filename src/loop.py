import base64
import binascii
import colorsys
import ctypes
import hashlib
import http.client
import math
import sys
import time
import traceback
import webbrowser
from more_itertools import locate
from zipfile import ZipFile
from tkinter import filedialog
from ctypes import POINTER, c_int

import OpenGL.GL as GL
import imgui
import pydub.exceptions
import sdl2
from pydub.exceptions import TooManyMissingFrames
from pydub.playback import _play_with_simpleaudio
from pypresence import Presence
from scipy.interpolate import \
    CubicSpline  # NOTE:  god i wish scipy had partial downloads like "scipy[interpolate]" like i don't need all of math to make. a spline

from src.level import *  # this is fine, i know what's there
from src.timings import import_timings

# Initialize constants

SCRIPT_DIR = str(Path(__file__).resolve().parent.parent)

FORMATS: tuple = (SSPMLevel, RawDataLevel, VulnusLevel)
FORMAT_NAMES: tuple = ("SS+ Map", "Raw Data", "Vulnus Map")
TIMING_GAMES = (
    "*.adofai",
    "*.osu",
    "*.chart"
)
FORMAT_EXTS: tuple = ("*.sspm", "*.txt", "*.json")
DIFFICULTIES: tuple = ("Unspecified", "Easy", "Medium", "Hard", "LOGIC?", "Tasukete")
HITSOUND = AudioSegment.from_file(f"{SCRIPT_DIR + os.sep}assets{os.sep}hit.wav").set_sample_width(2)
MISSSOUND = AudioSegment.from_file(f"{SCRIPT_DIR + os.sep}assets{os.sep}miss.wav").set_sample_width(2)
METRONOME_M = AudioSegment.from_file(f"{SCRIPT_DIR + os.sep}assets{os.sep}metronome_measure.wav").set_sample_width(2)
METRONOME_B = AudioSegment.from_file(f"{SCRIPT_DIR + os.sep}assets{os.sep}metronome_beat.wav").set_sample_width(2)
VAR_TYPES = ["8-bit Unsigned Integer",
             "16-bit Unsigned Integer",
             "32-bit Unsigned Integer",
             "64-bit Unsigned Integer",
             "Float",
             "Double",
             "Position",
             "Short Bytes",
             "Short String",
             "Long Bytes",
             "Long String",
             "Array"]
VAR_DEFAULTS = [0, 0, 0, 0, 0.0, 0.0, (0.0, 0.0), b"", "", b"", "", [[0, 1, 1]]]


class DummyRPC:
    """
    For when the user doesn't have internet.
    """

    def __init__(self):
        pass

    def connect(self):
        pass

    def update(self, *args, **kwargs):
        pass


class DelayedRect:
    def __init__(self, box: tuple[int, int, int, int], color: int, filled: bool = True, thickness: float = 1):
        self.box = box
        self.color = color
        self.filled = filled
        self.thickness = thickness

    def draw(self, draw_list):
        if self.filled:
            draw_list.add_rect_filled(*self.box, self.color)
        else:
            draw_list.add_rect(*self.box, self.color, self.thickness)


def spline(nodes, count):
    nodes = [(key, *value) for key, value in sorted(nodes.items())]
    nodes = np.array(nodes, dtype=np.float64)
    notes = {}
    start = min(nodes[:, 0])
    end = max(nodes[:, 0])
    cs = CubicSpline(nodes[:, 0], nodes[:, 1:])
    for time in np.linspace(start, end, count):
        notes[time] = cs(time)
    return notes


def play_at_position(audio, position):
    try:
        cut_audio = audio[int(position * 1000):]
    except TooManyMissingFrames:
        return None
    return _play_with_simpleaudio(cut_audio)


def adjust(x, s): return (((round(((x) / 2) * (s - 1)) / (s - 1)) * 2)) if s != 0 else x


def tuplehash(v):
    x = 0x345678
    mult = 1000003
    l = len(v)
    for i, ob in enumerate(v, 1):
        y = int.from_bytes(hashlib.sha256(ob.to_bytes(math.ceil(math.log(ob, 256)), "little")).digest(), "little")
        x = ((x ^ y) * mult)
        mult += (82520 + 2 * (l - i))
    x += 97531
    return x % (2**64)


def get_time_color():
    r, g, b = colorsys.hsv_to_rgb(time.time() / 3, .375, 1)
    return 0xFF000000 | (int(r * 255) << 16) | (int(g * 255) << 8) | int(b * 255)


class Editor:
    def __init__(self):
        self.displayed_markers = []
        self.adding_marker_type = ""
        self.adding_field = ""
        self.background_size = (0, 0)
        self.times_to_display = None
        self.notes_changed = False
        self.starting_position = None
        self.starting_time = None
        self.GITHUB_ICON_ID = None
        self.COVER_ID = None
        self.NO_COVER = None
        self.BACKGROUND = None
        self.menu_choice = None
        self.hitsounds = True
        self.bpm_markers = True
        self.io = None
        self.bpm = 120
        self.offset = 0
        self.approach_rate = 1100
        self.approach_distance = 30
        self.snapping = None
        self.level_window_size = (200, 200)
        self.filename = None
        self.temp_filename = None
        self.files = None
        self.preview_mode = False
        self.file_choice = -1
        self.current_folder = str(Path.home())
        self.level = None
        self.time = 0
        self.playing = False
        self.changed_since_save = False
        self.playback = None
        self.time_signature = (4, 4)
        self.beat_divisor = 4
        self.note_snapping = 3, 3
        self.draw_notes = True
        self.draw_audio = False
        self.fps_cap = 100
        self.vsync = False
        self.rects_drawn = 0
        self.rounding = 0
        self.volume = 0
        self.waveform_res = 4
        self.timeline_height = 50
        self.hitsound_offset = 0
        self.metronome = False
        self.cursor = True
        self.colors = []
        self.camera_pos = [0, 0]
        self.parallax = 0
        self.timings = np.array((), dtype=np.int64)
        self.time_since_last_change = time.time()
        # Read colors from file
        if os.path.exists(f"{SCRIPT_DIR + os.sep}colors.txt"):
            with open(f"{SCRIPT_DIR + os.sep}colors.txt", "r") as f:
                for line in f.read().splitlines():
                    color = int(line[1:], base=16)
                    if color <= 0xFFFFFF:
                        color |= 0xFF000000
                    # ARGB -> ABGR
                    r, g, b, a = (color & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF), ((color >> 24) & 0xFF)
                    color = a << 24 | r << 16 | g << 8 | b
                    self.colors.append(color)
        else:
            with open(f"{SCRIPT_DIR + os.sep}colors.txt", "w") as f:
                f.write("#FFFFFFFF")
            self.colors = [0xFFFFFFFF]
        self.swing = 0.5
        self.hitsound_panning = 1.0
        self.vis_map_size = 3
        self.audio_speed = 1
        self.error = None
        self.playtesting = False
        self.sensitivity = 2.0
        self.unique_label_counter = 0
        self.RPC = Presence(1032430090505703486)
        self.displayed_markers = []

    def speed_change(self, sound, speed=1.0):
        if speed < 0:
            sound = sound.reverse()
        try:
            assert sound.duration_seconds / speed < 3600, "The audio that was going to be played is too large.\nIf you want to circumvent this check, go to line 133 in src/loop.py and remove lines 211 through 220."
            assert abs(
                speed) * sound.frame_rate < 2147483647, "The audio that was going to be played is too fast, and the speed in samples can't be converted to a C integer."
        except AssertionError as e:
            self.error = e
            self.playing = False
            return AudioSegment.silent(duration=1)
        sound_with_altered_frame_rate = sound._spawn(sound.raw_data, overrides={
            "frame_rate": int(sound.frame_rate * abs(speed))
        })
        return sound_with_altered_frame_rate.set_frame_rate(sound.frame_rate)

    def adjust_swing(self, beat):
        b = (beat % 2)
        s = self.swing
        if b < (2 * s):
            return (beat - b) + (((2 - 2 * s) / (2 * s)) * b)
        else:
            return (beat - b) + (((2 * s) / (2 - 2 * s)) * (b - 2 * s) + 2 - 2 * s)

    def display_marker_type(self, index, name, types, readonly=False):
        any_changed = False
        if not isinstance(types, list):
            types = list(types)
        elabel = '-'.join([str(n) for n in index])
        if readonly:
            imgui.push_style_color(imgui.COLOR_TEXT, 1, 1, 1, 0.7)
        changed, value = imgui.input_text(f"Name##{elabel}", name, 256, imgui.INPUT_TEXT_READ_ONLY if readonly else 0)
        if changed and not readonly:
            any_changed = True
            name = value
        imgui.indent()
        for i, m_type in enumerate(types):
            changed, value = imgui.combo(f"Type##{i}-{elabel}", m_type - 1, VAR_TYPES[:-1]) if not readonly else \
                imgui.input_text(f"Type##{i}-{elabel}", VAR_TYPES[m_type - 1], 128, imgui.INPUT_TEXT_READ_ONLY)
            if changed and not readonly:
                any_changed = True
                types[i] = value + 1
            if not readonly:
                imgui.same_line()
                if imgui.button("-", 26, 26):
                    del types[i]
                    any_changed = True
        if not readonly and imgui.button(f"Add Type##{elabel}"):
            types.append(1)
            any_changed = True
        imgui.unindent()
        if readonly:
            imgui.pop_style_color()

        return any_changed, name, types

    def display_variable(self, index, var, var_type, arr_type=None, _from_array=False):
        elabel = '-'.join([str(n) for n in index])
        value = var
        if not _from_array:
            changed, value = imgui.combo(f"Type##{elabel}", var_type - 1, VAR_TYPES)
            if changed:
                return (True, None, value + 1, arr_type)
        if var is None:
            var = VAR_DEFAULTS[var_type - 1]
        if var_type in range(1, 5):
            changed, value = imgui.input_text(f"Value##int-{elabel}", str(var), 256,
                                              flags=imgui.INPUT_TEXT_CHARS_DECIMAL)  # imgui only goes up to 2**32
            try:
                value = int(value)
            except ValueError:
                value = var
            value = value % (16 ** (2 ** var_type))
        elif var_type in [5, 6]:
            changed, value = imgui.input_double(f"Value##double-{elabel}", var, 0, format="%.5f")
        elif var_type == 7:
            changed, value = imgui.input_float2(f"Value##float2-{elabel}", *var, "%.2f")
        elif var_type in range(8, 12):
            if var_type > 10:
                f = imgui.input_text_multiline
                l = 65536
            else:
                f = imgui.input_text
                l = 256
            if not var_type % 2:
                l = math.ceil(l * 1.33334)
                v = base64.b64encode(var).decode("utf-8")
            else:
                v = var
            changed, value = f(f"Value##{elabel}", v, l)
            if changed and not var_type % 2:
                try:
                    value = base64.b64decode(value)
                except binascii.Error:
                    changed = False
        else:
            if arr_type is None:
                arr_type = 1
            changed, arr_value = imgui.combo("Array Type", arr_type - 1, VAR_TYPES[:-1])
            if changed:
                value = [[None, 0, 0] for _ in range(len(var))]  # * len(var) doesn't work
                var_type = var_type
                arr_type = arr_value + 1
            else:
                imgui.indent()
                for i, val in enumerate(var):
                    vl, vr_t, ar_t = val
                    vr_t = arr_type
                    c, v, v_t, a_t = self.display_variable([*index, i], vl, vr_t, ar_t, _from_array=True)
                    if c:
                        var[i][0] = v
                        var[i][1] = v_t
                        var[i][2] = a_t
                        changed = True
                        value = var
                    imgui.same_line()
                    if imgui.button(f"-##{elabel}-del-arr", 26, 26):
                        del var[i]
                        changed = True
                        value = var
                if imgui.button(f"+##{elabel}-add-arr", 26, 26):
                    var.append([None, var_type, arr_type])
                    changed = True
                    value = var
                imgui.unindent()
        return changed, value, var_type, arr_type

    def display_sspm(self):
        """Display the edit menu for SSPM levels."""
        # Difficulty picker
        if isinstance(self.level.difficulty, str):
            try:
                self.level.difficulty = DIFFICULTIES.index(self.level.difficulty) - 1
            except:
                self.level.difficulty = -1
        changed, value = imgui.combo("Difficulty", self.level.difficulty + 1,
                                     list(DIFFICULTIES))
        if changed:
            self.level.difficulty = value - 1
            self.changed_since_save = True
        imgui.separator()
        changed, value = imgui.input_text("ID", self.level.id, 128,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if changed:
            self.level.id = value
            self.changed_since_save = True
        changed, value = imgui.input_text("Map Name", self.level.name, 128,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if changed:
            self.level.name = value
            self.changed_since_save = True
        changed, value = imgui.input_text("Song Name", self.level.song_name, 128,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if changed:
            self.level.song_name = value
            self.changed_since_save = True
        changed, value = imgui.input_text("Mappers", ", ".join(self.level.authors), 256,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if changed:
            self.level.authors = value.split(", ")
            self.changed_since_save = True
        imgui.separator()
        clicked = imgui.image_button(self.COVER_ID, 192, 192, frame_padding=0)
        if clicked:
            changed, value = self.open_file_dialog(
                {"Image": "*.png *.jpg *.bmp *.gif *.webp"})
            if changed:
                with Image.open(value) as im:
                    self.level.cover = im.copy()
                    self.create_image(self.level.cover, self.COVER_ID)
                self.changed_since_save = True
                self.time_since_last_change = time.time()
        if imgui.is_item_hovered():
            imgui.set_tooltip("Click to set a cover.")
        clicked = imgui.button("Remove Cover")
        if clicked:
            self.create_image(self.NO_COVER, self.COVER_ID)  # Remove the cover
            self.level.cover = None
            self.changed_since_save = True
        imgui.separator()
        # custom_fields=fields, marker_types=marker_types, markers=markers,
        #                            modchart=modchart, rating=rating
        changed, value = imgui.checkbox("Modchart?", self.level.modchart)
        if changed:
            self.level.modchart = value
        changed, value = imgui.input_int("Rating", self.level.rating, 0)
        if changed:
            self.level.rating = value
        expanded, visible = imgui.collapsing_header("Custom Fields")
        if expanded:
            fields = list(self.level.custom_fields.items())
            for i, (field, value) in enumerate(fields):
                if field in ["bpm", "offset", "swing", "time_signature_num", "time_signature_den"]:
                    continue
                name_changed, name_value = imgui.input_text(f"Name##{i}", field, 256)
                if name_changed and name_value not in self.level.custom_fields:
                    fields[i] = (name_value, fields[i][1])
                imgui.same_line()
                if imgui.button("-##del-field", 26, 26):
                    del fields[i]
                imgui.indent()
                changed, value, value_type, arr_type = self.display_variable([i], *value)
                if changed:
                    fields[i] = (field, (value, value_type, arr_type))
                imgui.unindent()
            changed, value = imgui.input_text("Add##add-field", self.adding_field, 256)
            if changed:
                self.adding_field = value
            imgui.same_line()
            if imgui.button("+##add-field", 26, 26) and self.adding_field != "":
                fields.append((self.adding_field, (0, 1, 1)))
                self.adding_field = ""
            self.level.custom_fields = dict(fields)
        expanded, visible = imgui.collapsing_header("Marker Types")
        if expanded:
            m_types = list(self.level.marker_types.items())
            any_changed = False
            for i, (name, types) in enumerate(m_types):
                changed, new_name, new_types = self.display_marker_type([i], name, types, name == "ssp_note")
                if changed:
                    any_changed = True
                    m_types[i] = [new_name, new_types]
            changed, value = imgui.input_text("Add##add-marker-type", self.adding_marker_type, 256)
            if changed:
                any_changed = True
                self.adding_marker_type = value
            imgui.same_line()
            if len(m_types) < 256 and imgui.button("+##add-marker-type", 26, 26) and self.adding_marker_type != "":
                any_changed = True
                m_types.append([self.adding_marker_type, []])
                self.adding_marker_type = ""
            if any_changed:
                self.level.marker_types = {"ssp_note": [7]} | {k: v for k, v in m_types if k != "ssp_note"}

    def display_vuln(self):
        """Display the edit menu for Vulnus levels."""
        if isinstance(self.level.difficulty, int):
            self.level.difficulty = DIFFICULTIES[self.level.difficulty + 1]
        changed, value = imgui.input_text("Difficulty", self.level.difficulty, 128)
        if changed:
            self.level.difficulty = value
            self.changed_since_save = True
        imgui.separator()
        split_name = self.level.name.split(" - ")
        fixed_name = False
        while len(split_name) < 2:
            split_name.append("???")
            fixed_name = True
        changed, value = imgui.input_text("Artist", split_name[0], 128,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if changed or fixed_name:
            self.level.name = value + " - " + split_name[1]
        changed, value = imgui.input_text("Title", split_name[1], 128,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if changed or fixed_name:
            self.level.name = split_name[0] + " - " + value
        changed, value = imgui.input_text("Mappers", ", ".join(self.level.authors), 256,
                                          imgui.INPUT_TEXT_AUTO_SELECT_ALL)
        if imgui.is_item_hovered():
            imgui.set_tooltip("Separate with spaces and commas.\n(e.g. \"Alice, Bob, Craig\")")
        if changed:
            self.level.authors = value.split(", ")
        imgui.separator()
        clicked = imgui.image_button(self.COVER_ID, 192, 192, frame_padding=0)
        if clicked:
            changed, value = self.open_file_dialog(
                {"Image": "*.png *.jpg *.bmp *.gif *.webp"})
            if changed:
                with Image.open(value) as im:
                    self.level.cover = im.copy()
                    self.create_image(self.level.cover, self.COVER_ID)
                self.changed_since_save = True
                self.time_since_last_change = time.time()
        if imgui.is_item_hovered():
            imgui.set_tooltip("Click to set a cover.")
        clicked = imgui.button("Remove Cover")
        if clicked:
            self.create_image(self.NO_COVER, self.COVER_ID)  # Remove the cover
            self.level.cover = None
            self.changed_since_save = True

    def open_file_dialog(self, extensions: dict[str, str]):
        v = filedialog.askopenfilename(title="Open a file",
                                       initialdir=self.current_folder,
                                       filetypes=tuple(extensions.items()))
        return bool(len(v)), v

    def save_file_dialog(self, suffix):
        v = filedialog.asksaveasfilename(title="Save a file",
                                         initialdir=self.current_folder,
                                         filetypes=tuple(suffix.items()))
        return bool(len(v)), v

    def keys(self):
        return tuple(self.io.keys_down)

    def time_scroll(self, y, keys, ms_per_beat):
        if self.level is not None:
            # Check modifier keys
            use_bpm = not (keys[sdl2.SDL_SCANCODE_LALT] or keys[sdl2.SDL_SCANCODE_RALT]) and (
                self.bpm != 0)  # If either alt key is pressed, or there's no bpm markers to base it off of
            if use_bpm:
                current_beat = (self.time) / (ms_per_beat)
                if keys[sdl2.SDL_SCANCODE_LSHIFT] or keys[sdl2.SDL_SCANCODE_RSHIFT]:
                    increment = self.time_signature[0]
                elif keys[sdl2.SDL_SCANCODE_LCTRL] or keys[sdl2.SDL_SCANCODE_RCTRL]:
                    increment = 1
                else:
                    increment = 1 / self.beat_divisor
                self.time = max((current_beat + increment * y) * ms_per_beat, 0)
            else:
                if keys[sdl2.SDL_SCANCODE_LSHIFT] or keys[sdl2.SDL_SCANCODE_RSHIFT]:
                    increment = 100
                elif keys[sdl2.SDL_SCANCODE_LCTRL] or keys[sdl2.SDL_SCANCODE_RCTRL]:
                    increment = 10
                else:
                    increment = 1
                self.time = max(self.time + increment * y, 0)

    def create_image(self, im, tex_id) -> int:
        texture_data = im.convert("RGBA").tobytes()  # Get the image's raw data for GL
        # Bind and set the texture at the id
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, im.size[0], im.size[1], 0, GL.GL_RGBA,
                        GL.GL_UNSIGNED_BYTE, texture_data)
        return tex_id  # NOTE: returning it makes things easier

    def snap_time(self):
        ms_per_beat = (60000 / self.bpm) * (4 / self.time_signature[1])
        step = (ms_per_beat) / self.beat_divisor
        self.time = math.floor((round(self.time / step) * (step)) - ((ms_per_beat - self.offset) % ms_per_beat))

    def load_file(self, filename):
        if Path(filename).suffix == ".sspm":
            level_class = SSPMLevel
        elif Path(filename).suffix == ".txt":
            level_class = RawDataLevel
        elif Path(filename).suffix == ".json":
            level_class = VulnusLevel
        else:
            self.error = AssertionError("Invalid level type!")
            return False
        # Read the level from the file and load it
        try:
            self.level, metadata = level_class.load(filename)
            if metadata is not None:
                # Load metadata
                self.bpm = metadata[0]
                self.offset = metadata[1]
                self.time_signature = metadata[2]
                self.swing = metadata[3]
        except Exception as e:
            self.error = e
            return False
        if self.error is None:
            self.notes_changed = True
            self.times_to_display = None
            # Initialize song variables
            self.create_image(
                self.NO_COVER if self.level.cover is None else self.level.cover.resize((192, 192), Image.LINEAR),
                self.COVER_ID)
            self.time = 0
            self.playing = False
            self.filename = filename
            self.timings = np.array((), dtype=np.int64)
            return True

    def start(self, window, impl, font, default_font, *_):
        self.io = imgui.get_io()

        event = sdl2.SDL_Event()

        # Initialize variables
        # Only connect if connected to the internet
        conn = http.client.HTTPSConnection("1.1.1.1", timeout=5)
        try:
            conn.request("HEAD", "/")
            self.RPC.connect()
        except:
            self.RPC = DummyRPC()
        start_time = time.time()
        running = True
        old_audio = None
        cursor = "arrow"
        sdl2_cursor = None
        audio_data = None
        space_last = False
        was_playing = False
        was_resizing_timeline = False
        last_hitsound_times = np.zeros((0), dtype=np.int64)
        old_mouse = (0, 0, 0, 0, 0)
        old_beat = 0
        tex_ids = GL.glGenTextures(3)  # NOTE: Update this when you add more images
        note_offset = None
        old_keys = self.keys()
        easter_egg_active = False  # feel free to enable this from here, but it's more fun if you find what makes it true w/o mofifying the code
        keys_pressed = []
        cursor_positions = [[0, 0]]
        level_was_active = False
        extent = 0
        spline_nodes = {}
        spline_display_notes = {}
        spline_amount = 5
        spline_window_open = False
        bulk_delete_window_open = False
        tap_timings_window_open = False
        bulk_delete_start_time = 0
        bulk_delete_end_time = 0
        cursor_spline = None
        name_id = -1
        timeline_width = 0
        dragging_timeline = False
        ms_per_beat = 0
        edit_markers_window_open = False
        marker_add_index = 0
        timings_quantize = True
        easter_egg_activated = False

        # Load constant textures
        with Image.open(f"{SCRIPT_DIR + os.sep}assets{os.sep}nocover.png") as im:
            self.NO_COVER = im.copy()
            self.COVER_ID = self.create_image(self.NO_COVER, int(tex_ids[0]))
        with Image.open(f"{SCRIPT_DIR + os.sep}assets{os.sep}github.png") as im:
            self.GITHUB_ICON_ID = self.create_image(im, int(tex_ids[1]))
        background_glob = glob.glob(f"{SCRIPT_DIR + os.sep}background.*")
        if len(background_glob):
            with Image.open(background_glob[0]) as im:
                self.BACKGROUND = self.create_image(im, int(tex_ids[2]))
                self.background_size = im.size
        # Handle opening a file with the program
        if len(sys.argv) > 1:
            self.load_file(sys.argv[1])
        while running:
            self.rects_drawn = 0
            dt = time.perf_counter_ns()
            # Check if the audio data needs to be updated
            if self.level is not None:
                if self.level.audio is not None:
                    if self.level.audio != old_audio:
                        audio_data = np.array(self.level.audio.get_array_of_samples())
                        extent = np.max(np.abs(audio_data))
                        old_audio = self.level.audio
            impl.process_inputs()
            imgui.new_frame()
            keys = self.keys()
            keys_changed = []
            if old_keys != keys:
                keys_changed = locate([a and not b for a, b in zip(keys, old_keys)])
                keys_changed = [*keys_changed]
                keys_pressed.extend(keys_changed)
                if tuplehash(keys_pressed) == 3693585790315968031:  # it's more fun if you find out how to do it legit but i won't be mad if you just remove this check
                    easter_egg_active = not easter_egg_active
                    imgui.open_popup("Easter Egg")
                    easter_egg_activated = True
                if len(keys_changed) and len(keys_pressed) > 64:
                    keys_pressed = keys_pressed[1:]
            mouse = tuple(self.io.mouse_down)
            if self.bpm:
                ms_per_beat = (60000 / self.bpm) * (4 / self.time_signature[1])
            # Check if the song needs to be paused/played
            if keys[sdl2.SDLK_SPACE] and self.level is not None and level_was_active:
                if not old_keys[sdl2.SDLK_SPACE]:
                    self.playing = not self.playing
                space_last = True
            elif space_last:
                space_last = False
            if self.playing and not was_playing:
                if self.level.audio is not None:
                    self.playback = play_at_position(
                        self.speed_change(self.level.audio + self.volume, self.audio_speed),
                        ((self.time) / 1000) / self.audio_speed)
                self.starting_time = time.perf_counter_ns()
                self.starting_position = self.time
            elif not self.playing and was_playing:
                if self.playback is not None:
                    del self.starting_time  # NOTE: Deleting these variables when they're not needed makes it easier to figure out that
                    del self.starting_position  # these are being accessed when they shouldn't be.
                    self.playback.stop()
                    self.playback = None
                if self.bpm:
                    # Snap the current time to the nearest quarter of a beat, for easier scrolling through
                    # TODO: make this snap with swing
                    self.snap_time()
            # Fix playback not working when playing in reverse (speed < 0)
            # This keeps going until it's being played
            if (self.playing
                    and self.playback is None
                    and self.level.audio is not None
                    and self.time / 1000 <= self.level.audio.duration_seconds):
                self.playback = play_at_position(self.speed_change(self.level.audio + self.volume, self.audio_speed),
                                                 ((self.time) / 1000) / self.audio_speed)
            # Set the window name
            # FIXME: The self.RPC code is kind of spaghetti.
            if sys.gettrace() is not None:
                if name_id != -1 or (time.time() % 15 < 0.1):
                    name_id = -1
                self.RPC.update(state="Developing", small_image="icon", start=start_time,
                                buttons=[{"label": "GitHub", "url": "https://github.com/balt-dev/SSpy/"}])
            elif self.level is None or (time.time() - self.time_since_last_change) > 600:  # Is a level open?
                if name_id != 0:
                    name_id = 0
                    if (time.time() - self.time_since_last_change) <= 600:  # Did they leave the app open?
                        sdl2.SDL_SetWindowTitle(window, "SSPy".encode("utf-8"))
                    self.RPC.update(state="Idling", small_image="icon", start=start_time,
                                    buttons=[{"label": "GitHub", "url": "https://github.com/balt-dev/SSpy/"}])
            elif self.filename is None:
                if name_id != 1 or (time.time() % 15 < 0.1):  # Does the level exist as a file?
                    name_id = 1
                    sdl2.SDL_SetWindowTitle(window, "*Unnamed - SSPy".encode("utf-8"))
                    self.RPC.update(details="Editing an unnamed level", small_image="icon",
                                    state=f"{self.level.get_end() / 1000:.1f} seconds long, {len(self.level.get_notes())} notes",
                                    start=start_time,
                                    buttons=[{"label": "GitHub", "url": "https://github.com/balt-dev/SSpy/"}])
            else:
                level_path = Path(self.filename).name
                if self.changed_since_save:
                    if name_id != 2 or (time.time() % 15 < 0.1):  # Has the level been saved?
                        name_id = 2
                        sdl2.SDL_SetWindowTitle(window, f"*{level_path} - SSPy".encode("utf-8"))
                        self.RPC.update(details=f"Editing {level_path}", small_image="icon",
                                        state=f"{self.level.get_end() / 1000:.1f} seconds long, {len(self.level.get_notes())} notes",
                                        start=start_time,
                                        buttons=[{"label": "GitHub", "url": "https://github.com/balt-dev/SSpy/"}])
                elif name_id != 3 or (time.time() % 15 < 0.1):
                    name_id = 3
                    sdl2.SDL_SetWindowTitle(window, f"{level_path} - SSPy".encode("utf-8"))
                    self.RPC.update(details=f"Editing {level_path}", small_image="icon",
                                    state=f"{self.level.get_end() / 1000:.1f} seconds long, {len(self.level.get_notes())} notes",
                                    start=start_time,
                                    buttons=[{"label": "GitHub", "url": "https://github.com/balt-dev/SSpy/"}])
            with imgui.font(font):
                while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
                    # Handle quitting the app
                    if event.type == sdl2.SDL_QUIT:
                        self.playing = False
                        if not self.changed_since_save:
                            running = False
                        else:
                            imgui.open_popup("quit.ensure")
                    if event.type == sdl2.SDL_MOUSEWHEEL and level_was_active and not self.playing:
                        self.time_scroll(event.wheel.y, keys, ms_per_beat)
                    impl.process_event(event)
                self.menu_choice = None
                # Handle file keybinds
                if keys[sdl2.SDL_SCANCODE_LCTRL] or keys[sdl2.SDL_SCANCODE_RCTRL]:
                    if keys[sdl2.SDLK_n] and not old_keys[sdl2.SDLK_n]:
                        # CTRL + N : New
                        self.notes_changed = True
                        self.times_to_display = None
                        self.level = SSPMLevel()
                        if self.playback is not None:
                            self.playback.stop()
                        self.playback = None
                        self.filename = None
                        self.playing = False
                        self.changed_since_save = True
                        self.time_since_last_change = time.time()
                        self.time = 0
                        self.create_image(
                            self.NO_COVER if self.level.cover is None else self.level.cover.resize((192, 192),
                                                                                                   Image.LINEAR),
                            self.COVER_ID)

                    if keys[sdl2.SDLK_o] and not old_keys[sdl2.SDLK_o]:
                        # CTRL + O : Open...
                        changed, value = self.open_file_dialog({k: v for k, v in zip(FORMAT_NAMES, FORMAT_EXTS)})
                        if changed:
                            self.load_file(value)
                    if keys[sdl2.SDLK_s] and not old_keys[sdl2.SDLK_s]:
                        # CTRL + S : Save / CTRL + SHIFT + S : Save As...
                        if self.filename is not None and not keys[sdl2.SDL_SCANCODE_LSHIFT]:
                            try:
                                self.level.save(self.filename, self.bpm, self.offset, self.time_signature, self.swing)
                                self.changed_since_save = False
                            except Exception as e:
                                self.error = e
                        else:
                            self.saveas()
                    if keys[sdl2.SDLK_p] and not old_keys[sdl2.SDLK_p]:
                        # CTRL + P : Preview
                        self.preview_mode = not self.preview_mode
                        if self.preview_mode:
                            self.menu_choice = "preview.alert"
                        if keys[sdl2.SDL_SCANCODE_LSHIFT]:
                            w, h = POINTER(c_int)(c_int(65535)), POINTER(c_int)(c_int(65535))  # woo! learned something
                            sdl2.SDL_GetWindowSize(window, w, h)
                            w, h = w[0], h[0]
                            sdl2.SDL_SetWindowSize(window, min(w, h), min(w, h))
                if not self.preview_mode and imgui.begin_main_menu_bar():
                    if imgui.begin_menu("File"):
                        if imgui.menu_item("New", "ctrl + n")[0]:
                            self.notes_changed = True
                            self.times_to_display = None
                            self.level = SSPMLevel()
                            if self.playback is not None:
                                self.playback.stop()
                            self.filename = None
                            self.playing = False
                            self.changed_since_save = True
                            self.time_since_last_change = time.time()
                            self.time = 0
                            self.create_image(
                                self.NO_COVER if self.level.cover is None else self.level.cover.resize((192, 192),
                                                                                                       Image.NEAREST),
                                self.COVER_ID)
                        if imgui.menu_item("Open...", "ctrl + o")[0]:
                            changed, value = self.open_file_dialog({k: v for k, v in zip(FORMAT_NAMES, FORMAT_EXTS)})
                            if changed:
                                self.load_file(value)
                        if imgui.menu_item("Save", "ctrl + s",
                                           enabled=(self.level is not None and self.filename is not None))[0]:
                            if self.filename is not None:
                                try:
                                    self.level.save(self.filename, self.bpm, self.offset, self.time_signature,
                                                    self.swing)
                                    self.changed_since_save = False
                                except Exception as e:
                                    self.error = e
                            else:
                                self.saveas()
                        if imgui.menu_item("Save As...", "ctrl + shift + s", enabled=self.level is not None)[0]:
                            if self.filename is not None:
                                self.temp_filename = self.filename
                            self.saveas()
                        imgui.separator()
                        if imgui.menu_item("Quit", "alt + f4")[0]:
                            self.playing = False
                            if not self.changed_since_save:
                                running = False
                            else:
                                self.menu_choice = "quit.ensure"  # NOTE: The quit menu won't open if I don't do this from here
                        imgui.end_menu()
                    if imgui.begin_menu("Edit", self.level is not None):
                        changed, value = imgui.combo("Format", FORMATS.index(self.level.__class__),
                                                     list(FORMAT_NAMES))
                        if changed:
                            self.level = FORMATS[value](self.level.name,
                                                        self.level.authors,
                                                        self.level.notes,
                                                        self.level.cover,
                                                        self.level.audio,
                                                        self.level.difficulty)
                            self.changed_since_save = True
                            self.time_since_last_change = time.time()
                        imgui.push_item_width(240)
                        if isinstance(self.level, SSPMLevel):
                            self.display_sspm()
                        elif isinstance(self.level, RawDataLevel):
                            changed, value = imgui.input_text("ID", self.level.id, 128,
                                                              imgui.INPUT_TEXT_AUTO_SELECT_ALL)
                            if changed:
                                self.level.id = value
                                self.changed_since_save = True
                                self.time_since_last_change = time.time()
                        elif isinstance(self.level, VulnusLevel):
                            self.display_vuln()
                        imgui.separator()
                        if self.level.audio is None:
                            imgui.text("/!\\ Map has no audio")
                        clicked = imgui.button("Change song")
                        if clicked:
                            # Load the selected audio
                            changed, value = self.open_file_dialog(
                                {"Audio": "*.mp3 *.ogg *.wav *.flac *.opus"})
                            if changed:
                                try:
                                    self.level.audio = AudioSegment.from_file(value).set_sample_width(2)
                                    self.changed_since_save = True
                                    self.time_since_last_change = time.time()
                                except pydub.exceptions.CouldntDecodeError:
                                    self.error = Exception("Audio file couldn't be read! It might be corrupted.")
                        imgui.pop_item_width()
                        imgui.separator()
                        changed, value = imgui.input_float("BPM", self.bpm, 0)
                        if changed:
                            self.bpm = max(min(value, 999999), 0)
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off beat snapping.")
                        if self.bpm != 0:
                            imgui.indent()
                            changed, value = imgui.input_int("Offset (ms)", self.offset, 0)
                            if changed:
                                self.offset = value
                            changed, value = imgui.checkbox("BPM markers?", self.bpm_markers)
                            if changed:
                                self.bpm_markers = value
                            changed, value = imgui.checkbox("Metronome?", self.metronome)
                            if changed:
                                self.metronome = value
                            changed, value = imgui.input_float("Swing", self.swing, 0)
                            if changed:
                                self.swing = min(max(0.001, value), 0.999)
                            imgui.unindent()
                            imgui.push_item_width(49)
                            # Display time signature
                            changed, value = imgui.input_int("", self.time_signature[0], 0)
                            if changed:
                                self.time_signature = (value, min(self.time_signature[1], 2048))
                            imgui.same_line()
                            imgui.text("/")
                            imgui.same_line()
                            changed, value = imgui.input_int("Time Signature", self.time_signature[1], 0)
                            if changed:
                                self.time_signature = (
                                    self.time_signature[0], min(max(value, 1), 256))
                            changed, value = imgui.input_int("Beat Divisor", self.beat_divisor, 0)
                            if changed:
                                self.beat_divisor = min(max(value, 1), 100000)
                        imgui.pop_item_width()
                        imgui.end_menu()
                    if imgui.begin_menu("Preferences", self.level is not None):
                        imgui.push_item_width(120)
                        changed, value = imgui.checkbox("Vsync?", self.vsync)
                        if changed:
                            sdl2.SDL_GL_SetSwapInterval(int(value))  # Turn on/off VSync
                            self.vsync = value
                        if not self.vsync:
                            imgui.indent()
                            changed, value = imgui.input_int("FPS Cap", self.fps_cap, 0)
                            if changed:
                                self.fps_cap = min(max(value, 15), 360)
                            imgui.unindent()
                        changed, value = imgui.checkbox("Draw notes on timeline?", self.draw_notes)
                        if changed:
                            self.draw_notes = value
                        changed, value = imgui.checkbox("Draw audio on timeline?", self.draw_audio)
                        if changed:
                            self.draw_audio = value
                        if self.draw_audio:
                            imgui.indent()
                            changed, value = imgui.slider_int("Waveform resolution (px)", self.waveform_res, 1, 20)
                            if changed:
                                self.waveform_res = value
                            imgui.unindent()
                        imgui.separator()
                        imgui.push_item_width(49)
                        # Display note snapping
                        changed, value = imgui.input_int("##", self.note_snapping[0], 0)
                        if changed:
                            self.note_snapping = (min(96, max(value, 0)) if value != 1 else 0, self.note_snapping[1])
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off snapping.")
                        imgui.same_line()
                        imgui.text("/")
                        imgui.same_line()
                        changed, value = imgui.input_int("Note Snapping", self.note_snapping[1], 0)
                        if changed:
                            self.note_snapping = (self.note_snapping[0], min(96, max(value, 0)) if value != 1 else 0)
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off snapping.")
                        imgui.pop_item_width()
                        changed, value = imgui.input_int("Approach Rate (ms)", self.approach_rate, 0)
                        if changed:
                            self.approach_rate = min(max(value, 50), 2000)
                        changed, value = imgui.input_int("Spawn Distance (units)", self.approach_distance, 0)
                        if changed:
                            self.approach_distance = min(max(value, 1), 100)
                        imgui.separator()
                        if not self.playing:
                            changed, value = imgui.input_int("Position (ms)", self.time, 0)
                            if changed:
                                self.time = abs(value)
                            if self.level.audio is not None:
                                changed, value = imgui.slider_float("Volume (db)", self.volume, -100, 10, "%.1f", 1.2)
                                if changed:
                                    self.volume = value
                            changed, value = imgui.input_float("Playback Speed", self.audio_speed, 0, format="%.2f")
                            if changed:
                                self.audio_speed = (max(min(value, 3.4e38), -3.4e38) if abs(value) > 0.05 else (
                                    value / abs(
                                        value)) * max(
                                    abs(value), 0.05)) if value != 0 else 0.05
                        changed, value = imgui.checkbox("Play hitsounds?", self.hitsounds)
                        if changed:
                            self.hitsounds = value
                        if self.hitsounds:
                            imgui.indent()
                            changed, value = imgui.input_int("Hitsound Offset (ms)", self.hitsound_offset, 0)
                            if changed:
                                self.hitsound_offset = value
                            changed, value = imgui.slider_float("Hitsound Panning", self.hitsound_panning, -1, 1,
                                                                "%.2f")
                            if changed:
                                self.hitsound_panning = value
                            imgui.unindent()
                        imgui.separator()
                        changed, value = imgui.checkbox("Show cursor?", self.cursor)
                        if changed:
                            self.cursor = value
                        if self.cursor:
                            imgui.indent()
                            changed, value = imgui.input_float("Parallax?", -self.parallax, 0, format="%.3f")
                            if changed:
                                self.parallax = -value
                            imgui.unindent()
                        changed, value = imgui.input_float("Map Size", self.vis_map_size, 0, format="%.2f")
                        if changed:
                            self.vis_map_size = max(value, 0.01)
                        changed, value = imgui.slider_int("Note Rounding", int(self.rounding * 100), 0, 100)
                        if changed:
                            self.rounding = value / 100
                        imgui.pop_item_width()
                        imgui.end_menu()
                    if imgui.begin_menu("Tools", self.level is not None):
                        if imgui.button("Offset Notes"):
                            self.menu_choice = "tools.offset_notes"
                        if imgui.button("Bulk Delete"):
                            bulk_delete_window_open = True
                        imgui.separator()
                        if imgui.button("Spline"):
                            spline_window_open = True
                        imgui.separator()
                        if isinstance(self.level, SSPMLevel) and imgui.button("Edit Markers"):
                            edit_markers_window_open = isinstance(self.level, SSPMLevel)
                        if imgui.button("Import Timings"):
                            changed, value = self.open_file_dialog({"Chart": " ".join(TIMING_GAMES)})
                            if changed:
                                timings_filepath = value
                                timings_game = TIMING_GAMES.index("*" + Path(value).suffix)
                                try:
                                    self.timings = np.array(import_timings(timings_filepath, timings_game), np.int64)
                                except Exception as e:
                                    self.error = e
                        if imgui.button("Tap Timings"):
                            tap_timings_window_open = True
                        if self.timings.size > 0:
                            imgui.indent()
                            if imgui.button("Clear Timings"):
                                self.timings = np.array((), dtype=np.int64)
                            imgui.unindent()
                        changed, value = imgui.checkbox("Playtesting?", self.playtesting)
                        if changed:
                            self.playtesting = value
                        if imgui.is_item_hovered():
                            imgui.set_tooltip(
                                "Note that there's a hit window of 1 ms, because it's much easier to just hook hit detection into the hitsound code.\nYou're not as bad as it looks, trust me.")
                        if self.playtesting:
                            changed, value = imgui.input_float("Sensitivity", self.sensitivity, 0, format="%.2f")
                            if changed:
                                self.sensitivity = value
                        imgui.end_menu()
                    if imgui.begin_menu("Info", self.level is not None):
                        imgui.text(f"Notes: {len(self.level.notes)}")
                        imgui.text(f"Length: {self.level.get_end() / 1000}")
                        imgui.end_menu()
                    if imgui.begin_menu("Help"):
                        imgui.text("Mouse wheel or left/right arrows to move your place on the timeline")
                        imgui.text("Space to play/pause the level")
                        imgui.text("Left click to place a note, right click to delete")
                        imgui.separator()
                        imgui.text(
                            "Place colors.txt in the script directory with a list of colors to customize note colors")
                        imgui.text(
                            "Place background.png (or .jpg, .webp, whatever) in the script directory to add a background")
                        imgui.end_menu()
                    source_code_was_open = imgui.core.image_button(self.GITHUB_ICON_ID, 26, 26, frame_padding=0)
                    if source_code_was_open:
                        webbrowser.open("https://github.com/balt-is-you-and-shift/SSpy", 2, autoraise=True)
                    imgui.end_main_menu_bar()
                # Handle popups
                if self.menu_choice is not None:
                    imgui.open_popup(self.menu_choice)
                if imgui.begin_popup("quit.ensure"):
                    imgui.text("You have unsaved changes!")
                    imgui.text("Are you sure you want to exit?")
                    if imgui.button("Quit"):
                        return False
                    imgui.same_line(spacing=10)
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()
                    imgui.end_popup()
                if imgui.begin_popup("tools.offset_notes"):
                    imgui.text("Offset all notes by a specified value.")
                    imgui.text("Current Time - Offset = New Time")
                    if note_offset is None:
                        note_offset = 0
                    changed, value = imgui.input_int("Offset", note_offset, 0)
                    if changed:
                        note_offset = value
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()
                    imgui.same_line(spacing=10)
                    if imgui.button("Confirm"):
                        self.notes_changed = True
                        self.times_to_display = None
                        # FIXME: this code kinda sucks
                        new_notes = {}
                        for timing, pos in self.level.notes.items():
                            new_notes[timing - note_offset] = pos
                        self.level.notes = new_notes
                        note_offset = None
                        self.changed_since_save = True
                        self.time_since_last_change = time.time()
                        imgui.close_current_popup()
                    imgui.end_popup()
                if imgui.begin_popup("preview.alert"):
                    imgui.text("You have just entered preview mode.")
                    imgui.text("This hides the timeline and menu bar.")
                    imgui.text("If you want to exit preview mode, press Ctrl+P once again.")
                    imgui.end_popup()
                if bulk_delete_window_open and imgui.begin("Bulk Delete"):
                    imgui.text("Delete all notes within a specified time slice.")
                    imgui.columns(2, border=False)
                    changed, value = imgui.input_int("Start Time", bulk_delete_start_time, 0)
                    if changed:
                        bulk_delete_start_time = value
                    imgui.core.set_column_width(-1, 260)
                    imgui.next_column()
                    if imgui.button("Set Here##start"):
                        bulk_delete_start_time = self.time
                    imgui.next_column()
                    changed, value = imgui.input_int("End Time", bulk_delete_end_time, 0)
                    if changed:
                        bulk_delete_end_time = value
                    imgui.next_column()
                    if imgui.button("Set Here##end"):
                        bulk_delete_end_time = self.time
                    imgui.columns(1)
                    if imgui.button("Cancel"):
                        bulk_delete_window_open = False
                    imgui.same_line(spacing=10)
                    if imgui.button("Confirm"):
                        self.notes_changed = True
                        self.times_to_display = None
                        times = np.array(tuple(self.level.notes.keys()))
                        times = times[np.logical_and(bulk_delete_start_time <= times, times <= bulk_delete_end_time)]
                        for note_time in times:
                            del self.level.notes[note_time]
                        self.changed_since_save = True
                        self.time_since_last_change = time.time()
                    imgui.end()
                if edit_markers_window_open:
                    if isinstance(self.level, SSPMLevel) and len(self.level.marker_types) > 1:
                        imgui.set_next_window_size(0, 0)
                        if imgui.begin("Markers"):
                            imgui.text("Edit markers within the level.")
                            imgui.separator()
                            changed, value = imgui.combo("##add-marker", marker_add_index,
                                                         [*self.level.marker_types][1:])
                            if changed:
                                marker_add_index = value
                            imgui.same_line()
                            if imgui.button("Add Here"):
                                self.level.markers.append(dict(time=self.time, m_type=marker_add_index + 1,
                                                               fields=[VAR_DEFAULTS[var_type - 1] for var_type in
                                                                       tuple(self.level.marker_types.values())[
                                                                           marker_add_index + 1]]))
                            imgui.separator()
                            for e, (i, marker) in enumerate(self.displayed_markers):
                                changed, value = imgui.combo(f"##edit-marker-{i}", marker["m_type"] - 1,
                                                             [*self.level.marker_types][1:])
                                if changed:
                                    self.level.markers[i] = dict(time=self.time, m_type=value + 1,
                                                                 fields=[VAR_DEFAULTS[var_type] for var_type in
                                                                         tuple(self.level.marker_types.values())[
                                                                             value + 1]])
                                imgui.same_line()
                                if imgui.button(f"-##remove-marker-{i}", 26, 26):
                                    del self.level.markers[i]
                                imgui.indent()
                                try:
                                    var_types = tuple(self.level.marker_types.values())[marker["m_type"]]
                                    assert len(marker["fields"]) == len(var_types)
                                    any_changed = False
                                    for j, field in enumerate(marker["fields"]):
                                        changed, value, *_ = self.display_variable([i, j], field, var_types[j], _from_array=True)
                                        if changed:
                                            any_changed = True
                                            marker["fields"][j] = value
                                    if any_changed:
                                        self.level.markers[i] = marker
                                        self.displayed_markers[e] = marker
                                except (TypeError, AssertionError):
                                    imgui.text_colored("! This marker type has changed, making this marker invalid.", 1, 0.25, 0.25)
                                    if imgui.button(f"Reset##reset-marker-{i}"):
                                        marker = dict(time=self.time, m_type=marker["m_type"],
                                                      fields=[VAR_DEFAULTS[var_type - 1] for var_type in
                                                              tuple(self.level.marker_types.values())[
                                                          marker["m_type"]]])
                                        self.level.markers[i] = marker
                                        self.displayed_markers[e] = marker
                                imgui.unindent()
                            if imgui.button("Close"):
                                edit_markers_window_open = False
                            imgui.end()
                    else:
                        edit_markers_window_open = False
                if spline_window_open:
                    imgui.set_next_window_size(0, 0)
                    if imgui.begin("Spline"):
                        imgui.text("Create a cubic spline curve from nodes.")
                        imgui.text("Press S to create a node on the playfield at the mouse.")
                        imgui.separator()
                        imgui.push_item_width(120)
                        imgui.columns(2)
                        imgui.separator()
                        imgui.text("Time")
                        imgui.set_column_width(-1, 120)
                        imgui.next_column()
                        imgui.text("Position")
                        imgui.separator()
                        imgui.next_column()

                        times = tuple(spline_nodes.keys())
                        spline_nodes = list(spline_nodes.items())
                        for i, (timing, position) in enumerate(spline_nodes):
                            changed, value = imgui.input_int(f"##{i}time", timing, 0)
                            if changed:
                                value = max(value, 0)
                                while value in times:
                                    value += 1
                                spline_nodes[i] = (value, position)
                            imgui.next_column()
                            changed, value = imgui.input_float2(f"##{i}pos", *position, format="%.3f")
                            if changed:
                                spline_nodes[i] = (timing, value)
                            imgui.same_line()
                            if imgui.button(f"-##{i}del", 26, 26):
                                del spline_nodes[i]
                            imgui.next_column()
                        if imgui.button(f"+##add", 26, 26):
                            add_time = self.time
                            while add_time in times:
                                add_time += 1
                            spline_nodes.append((add_time, (0, 0)))
                        spline_nodes = dict(spline_nodes)
                        imgui.columns(1)
                        imgui.separator()
                        changed, value = imgui.input_int("Notes on Path", spline_amount, 0)
                        if changed:
                            spline_amount = max(2, value)
                        if imgui.button("Close"):
                            spline_nodes = {}
                            spline_display_notes = {}
                            spline_amount = 5
                            spline_window_open = False
                        imgui.same_line(spacing=10)
                        if len(spline_nodes) > 1:
                            spline_display_notes = spline(spline_nodes, spline_amount)
                            if imgui.button("Place"):
                                self.notes_changed = True
                                self.times_to_display = None
                                for timing, position in spline_display_notes.items():
                                    if timing in self.level.notes:
                                        self.level.notes[int(timing)].append(position)
                                    else:
                                        self.level.notes[int(timing)] = [position]
                                self.changed_since_save = True
                                self.time_since_last_change = time.time()
                        imgui.pop_item_width()
                        imgui.end()
                if tap_timings_window_open:
                    imgui.set_next_window_size(0, 0)
                    if imgui.begin("Tap Timings"):
                        imgui.text("Tap out timings to use in the level.")
                        imgui.separator()
                        if self.bpm != 0:
                            changed, value = imgui.checkbox("Quantize to BPM?", timings_quantize)
                            if changed:
                                timings_quantize = value
                        else:
                            timings_quantize = False
                        _, _ = imgui.input_text("##timing-tap", "Focus here and tap to add timings.", 256, imgui.INPUT_TEXT_READ_ONLY)
                        if imgui.is_item_active() and len(keys_changed) > 0:
                            if not self.playing:
                                self.playing = True
                                if self.level.audio is not None:
                                    self.playback = play_at_position(
                                        self.speed_change(self.level.audio + self.volume, self.audio_speed),
                                        ((self.time) / 1000) / self.audio_speed)
                                self.starting_time = time.perf_counter_ns()
                                self.starting_position = self.time
                            set_timing = self.time
                            if timings_quantize:
                                set_timing = round((set_timing - self.offset) / (ms_per_beat / self.beat_divisor)) * (ms_per_beat / self.beat_divisor)
                            self.timings = np.unique(np.append(self.timings, int(set_timing)))
                        if imgui.button("Done"):
                            tap_timings_window_open = False
                        imgui.end()
                if self.level is not None:
                    size = self.io.display_size
                    imgui.set_next_window_size(size[0], size[1] - (0 if self.preview_mode else 26))
                    imgui.set_next_window_position(0, 0 if self.preview_mode else 26)
                    mouse_pos = tuple(self.io.mouse_pos)
                    imgui.push_style_var(imgui.STYLE_WINDOW_PADDING, (0, 0))
                    if imgui.core.begin("Level",
                                        flags=imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_COLLAPSE | imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS):
                        x, y = imgui.get_window_position()
                        w, h = imgui.get_content_region_available()
                        timeline_rects = []
                        if imgui.begin_child("nodrag", 0, 0, False, ):
                            level_was_active = imgui.is_window_focused()
                            if level_was_active and (keys[sdl2.SDL_SCANCODE_LEFT] or keys[sdl2.SDL_SCANCODE_RIGHT]) and not \
                                    (old_keys[sdl2.SDL_SCANCODE_LEFT] or old_keys[sdl2.SDL_SCANCODE_RIGHT]):
                                self.time_scroll((2 * keys[sdl2.SDL_SCANCODE_RIGHT]) - 1, keys, ms_per_beat)
                            draw_list = imgui.get_window_draw_list()
                            if not dragging_timeline:
                                timeline_width = max(self.level.get_end() + 1000, self.time + self.approach_rate, 1)
                            # Draw the main UI background
                            square_side = min(w, h)
                            if self.BACKGROUND is None:
                                draw_list.add_rect_filled(x, y, x + w, y + h, 0xff000000)
                            else:
                                # Adjust width and height for UVs
                                adjusted_w = w / self.background_size[0]
                                adjusted_h = h / self.background_size[1]
                                normalized_w = adjusted_w / max(adjusted_w, adjusted_h)
                                normalized_h = adjusted_h / max(adjusted_w, adjusted_h)
                                draw_list.add_image(self.BACKGROUND, (x, y), (x + w, y + h),
                                                    (0.5 - (normalized_w / 2), 0.5 - (normalized_h / 2)),
                                                    (0.5 + (normalized_w / 2), 0.5 + (normalized_h / 2)))
                            adjusted_x = (((x + w) / 2) - (square_side / 2))
                            adjusted_y = (((y + h) / 2) - (square_side / 2))
                            box = (adjusted_x, adjusted_y, adjusted_x + square_side, adjusted_y + square_side)
                            timeline_rects.append(
                                DelayedRect((x, (y + h) - (0 if self.preview_mode else self.timeline_height), x + w, (y + h)), 0x80404040))
                            self.rects_drawn += 3
                            note_pos = [(((mouse_pos[0] - (adjusted_x)) / (square_side)) * self.vis_map_size) - (
                                self.vis_map_size / 2) + 1,
                                (((mouse_pos[1] - (adjusted_y)) / (square_side)) * self.vis_map_size) - (
                                self.vis_map_size / 2) + 1]
                            cursor_pos = (
                                ((note_pos[0] - 1) * self.sensitivity) + 1, ((note_pos[1] - 1) * self.sensitivity) + 1)
                            note_pos[0] -= self.camera_pos[0]
                            note_pos[1] -= self.camera_pos[1]
                            if ((not self.preview_mode) and self.level.audio is not None and audio_data is not None
                                    and self.draw_audio and self.timeline_height > 20):
                                center = (y + h) - (self.timeline_height / 2)
                                length = int(self.level.audio.frame_rate * timeline_width / 1000)
                                waveform_width = int(
                                    size[0])
                                # Draw waveform
                                # FIXME: it'd be nice if this wasn't a python loop
                                for n in range(0, waveform_width, self.waveform_res):
                                    try:
                                        # Slice a segment of audio
                                        sample = audio_data[math.floor((n / waveform_width) * length * 2): math.floor(
                                            ((n + self.waveform_res) / waveform_width) * length * 2)]
                                        timeline_rects.append(DelayedRect(
                                            (x + int((w / waveform_width) * n),
                                             center + int(
                                                 (np.max(sample) / (extent / 0.8)) * (
                                                     self.timeline_height // 2)),
                                             x + int((w / waveform_width) * n) + self.waveform_res,
                                             center + int(
                                                 (np.min(sample) / (extent / 0.8)) * (
                                                     self.timeline_height // 2))),
                                            0x20ffffff))
                                        self.rects_drawn += 1
                                    except (IndexError, ValueError):
                                        break
                            if not self.preview_mode and self.draw_notes and self.times_to_display is not None:
                                # Draw notes
                                for i, note in enumerate(self.times_to_display):
                                    color = (self.colors[i % len(self.colors)] & 0xFFFFFF) | 0x40000000
                                    progress = note / timeline_width
                                    progress = progress if not math.isnan(progress) else 1
                                    timeline_rects.append(
                                        DelayedRect((x + int(w * progress), (y + h) - self.timeline_height,
                                                     x + int(w * progress) + 1,
                                                     (y + h) - (self.timeline_height * 0.8)),
                                                    color))
                                    self.rects_drawn += 1
                            # Draw currently visible area on timeline
                            start = (self.time) / timeline_width
                            end = (self.time + self.approach_rate) / timeline_width
                            timeline_rects.append(
                                DelayedRect((x + int(w * start), (y + h) - self.timeline_height, x + int(w * end) + 1,
                                             (y + h)), 0x80ffffff, thickness=3, filled=False))
                            self.rects_drawn += 1

                            def center_of_view(text):
                                text_width = imgui.calc_text_size(text).x
                                return max(
                                    min((((x + int(w * start)) + (x + int(w * end) + 1)) / 2) - (text_width / 2),
                                        w - text_width), text_width / 2)

                            # Draw the current time above the visible area
                            if not self.preview_mode:
                                draw_list.add_text(
                                    center_of_view(f"{self.time / 1000:.3f}"),
                                    y + h - (self.timeline_height + 20), 0x80FFFFFF, f"{self.time / 1000:.3f}")
                                if self.bpm:
                                    # Draw the current measure and beat
                                    raw_current_beat = (self.time - self.offset) / (ms_per_beat)
                                    current_beat = self.adjust_swing(raw_current_beat)
                                    m_text = f"Measure {current_beat // self.time_signature[0]:.0f}"
                                    draw_list.add_text(
                                        center_of_view(m_text),
                                        y + h - (self.timeline_height + 60), 0x80FFFFFF, m_text)
                                    b_text = f"Beat {f'{current_beat % (self.time_signature[0] / (self.time_signature[1] / 4)):.2f}'.rstrip('0').rstrip('.')}"
                                    draw_list.add_text(
                                        center_of_view(b_text),
                                        y + h - (self.timeline_height + 40), 0x80FFFFFF, b_text)

                                    floor_beat = math.floor(raw_current_beat)
                                    # Play the metronome
                                    if self.metronome and self.playing:
                                        beat_skipped = floor_beat - math.floor(old_beat)
                                        if beat_skipped:
                                            if old_beat // self.time_signature[0] != current_beat // self.time_signature[
                                                    0]:  # If a measure has passed
                                                _play_with_simpleaudio(METRONOME_M)
                                            else:
                                                _play_with_simpleaudio(METRONOME_B)
                                    old_beat = current_beat
                                    # Draw markers
                                    if isinstance(self.level, SSPMLevel):
                                        old_time = -1
                                        offset = 0
                                        self.displayed_markers = []
                                        for i, marker in enumerate(self.level.markers):  # XXX: this isn't very good
                                            if marker["time"] == old_time:
                                                offset += 1
                                            else:
                                                offset = 0
                                                old_time = marker["time"]
                                            if self.time <= marker["time"] < (self.time + self.approach_rate):
                                                line_prog = 1 - ((marker["time"] - self.time) / self.approach_rate)
                                                draw_list.add_line(
                                                    *self.note_pos_to_abs_pos(
                                                        (self.vis_map_size / 2 + 1,
                                                         (self.vis_map_size / 2 + 1) + (0.05 * offset)),
                                                        box, line_prog),
                                                    *self.note_pos_to_abs_pos(
                                                        (self.vis_map_size / -2 + 1,
                                                         (self.vis_map_size / 2 + 1) + (0.05 * offset)),
                                                        box, line_prog),
                                                    0xFFFFFF | (int(0xFF * max(0, line_prog)) << 24),
                                                    thickness=4 * line_prog
                                                )
                                            progress = marker["time"] / timeline_width
                                            timeline_rects.append(
                                                DelayedRect((x + int(w * progress), (y + h) - self.timeline_height * 0.2,
                                                             x + int(w * progress) + 1,
                                                             (y + h) - self.timeline_height * 0.4),
                                                            0x00ff00ff))
                                            if self.time == marker["time"]:
                                                self.displayed_markers.append((i, marker))
                                            self.rects_drawn += 1

                                    if self.bpm_markers:
                                        # Draw beat markers on timeline
                                        end_beat = (timeline_width / ms_per_beat)
                                        for beat in range(int(end_beat * self.beat_divisor + 1), 0, -1):
                                            beat /= self.beat_divisor
                                            on_measure = not (beat % self.time_signature[0])
                                            on_beat = not (beat % 1)
                                            self.swing = 1 - self.swing  # Invert this because it draws in the wrong place otherwise
                                            swung_beat = self.adjust_swing(beat)
                                            self.swing = 1 - self.swing
                                            beat_time = (swung_beat * ms_per_beat) + self.offset
                                            if (end_beat < 250 or on_beat) and (
                                                    end_beat < 500 or on_measure) and end_beat < 2000:
                                                progress = beat_time / timeline_width
                                                progress = progress if not math.isnan(progress) else 1
                                                timeline_rects.append(DelayedRect((x + int(w * progress), (y + h) - (
                                                    self.timeline_height * (
                                                        0.3 if on_measure else 0.2 if on_beat else 0.1)),
                                                    x + int(w * progress) + 1, (y + h)),
                                                    0xff0000ff if on_measure else 0x800000ff))
                                                self.rects_drawn += 1
                                            if (self.time <= beat_time < self.time + self.approach_rate):
                                                line_prog = 1 - ((beat_time - self.time) / self.approach_rate)
                                                # Draw beat marker in note space
                                                draw_list.add_rect(
                                                    *self.note_pos_to_abs_pos(
                                                        (self.vis_map_size / 2 + 1, self.vis_map_size / 2 + 1),
                                                        box, line_prog),
                                                    *self.note_pos_to_abs_pos(
                                                        (self.vis_map_size / -2 + 1, self.vis_map_size / -2 + 1),
                                                        box, line_prog),
                                                    0xFF | (int(0xFF * max(0, line_prog) / (
                                                        1 if on_measure else 2 if on_beat else 6))) << 24,
                                                    thickness=2 * max(0, line_prog) * (2 if on_measure else 1)
                                                )
                                                self.rects_drawn += 1
                                for i, timing in enumerate(self.timings[np.logical_and(self.time <= self.timings, self.timings < (self.time + self.approach_rate))]):
                                    progress = timing / timeline_width
                                    if progress < 1:
                                        progress = progress if not math.isnan(progress) else 1
                                        line_prog = 1 - ((timing - self.time) / self.approach_rate)
                                        # Draw beat marker in note space
                                        draw_list.add_line(
                                            *self.note_pos_to_abs_pos(
                                                (self.vis_map_size / 2 + 1, self.vis_map_size / -2 + 1),
                                                box, line_prog),
                                            *self.note_pos_to_abs_pos(
                                                (self.vis_map_size / -2 + 1, self.vis_map_size / -2 + 1),
                                                box, line_prog),
                                            0xFF00 | int(0xFF * max(0, line_prog)) << 24,
                                            thickness=2 * max(0, line_prog)
                                        )
                                        self.rects_drawn += 1
                            if self.times_to_display is not None:
                                # FIXME: Copy the times display for hitsound offsets :(
                                hitsound_times = self.times_to_display[np.logical_and(
                                    self.times_to_display >= int(self.time) + (
                                        self.hitsound_offset / self.audio_speed) - 1,
                                    (self.times_to_display) < (
                                        int(self.time) + self.approach_rate + (
                                            self.hitsound_offset * self.audio_speed)))].flatten()
                                note_times = self.times_to_display[
                                    np.logical_and(self.times_to_display - self.time >= 0,
                                                   (self.times_to_display) < (
                                                       self.time + self.approach_rate))].flatten()
                                for note_time in note_times[::-1]:
                                    i = np.where(self.times_to_display == note_time)[0][0]
                                    for note in self.level.notes[note_time]:
                                        rgba = self.colors[i % len(self.colors)]
                                        rgb, a = rgba & 0xFFFFFF, (rgba & 0xFF000000) >> 24
                                        progress = 1 - ((note_time - self.time) / self.approach_rate)
                                        self.draw_note(draw_list, note,
                                                       box, progress,
                                                       color=rgb, alpha=a)

                                # Play note hit sound
                                if self.playing and self.hitsounds:
                                    if ((last_hitsound_times.size and
                                         np.min(last_hitsound_times) < self.time + (
                                             self.hitsound_offset / self.audio_speed) - 1)):
                                        notes = self.level.notes[np.min(last_hitsound_times)]
                                        for note in notes[:8]:
                                            pos = note[0] - 1
                                            panning = (pos / (self.vis_map_size / 2)) * self.hitsound_panning
                                            if not self.playtesting or (abs(note[0] - cursor_pos[0]) < (0.57) and abs(
                                                    note[1] - cursor_pos[1]) < (0.57)):
                                                _play_with_simpleaudio(HITSOUND.pan(min(max(panning, -1), 1)))
                                            else:
                                                _play_with_simpleaudio(MISSSOUND.pan(min(max(panning, -1), 1)))
                                last_hitsound_times = hitsound_times
                            # XXX: copy/pasted code :/
                            if len(spline_display_notes) and spline_window_open:
                                if len(spline_nodes) > 1:
                                    for note_time, note in tuple(spline_nodes.items())[
                                            ::-1]:  # Invert to draw from back to front
                                        progress = 1 - ((note_time - self.time) / self.approach_rate)
                                        if 0 < progress < 1.01:
                                            handle_size = ((square_side / self.vis_map_size) / 1.25) * (
                                                1 / (1 + ((1 - progress) * self.approach_distance)))
                                            abs_position = self.note_pos_to_abs_pos(note,
                                                                                    box,
                                                                                    progress)
                                            draw_list.add_circle_filled(*abs_position, handle_size / 8,
                                                                        (int(0x80 * progress) << 24) | 0x00FFFF)

                                    for note_time in tuple(spline_display_notes.keys())[
                                            ::-1]:  # Invert to draw from back to front
                                        note = spline_display_notes[note_time]
                                        progress = 1 - ((note_time - self.time) / self.approach_rate)
                                        self.draw_note(draw_list, note,
                                                       box, progress,
                                                       color=0xFFFF00, alpha=int(0x80 * progress), size=0.5)

                            if level_was_active and mouse_pos[
                                    1] < y + h - 5 - (0 if self.preview_mode else self.timeline_height):
                                sdl2.SDL_ShowCursor(
                                    not (self.playtesting and imgui.is_window_focused() and imgui.is_window_hovered()))
                                # Note placing and deleting
                                time_arr = np.array(tuple(self.level.notes.keys()))
                                time_arr = time_arr[
                                    np.logical_and(time_arr - self.time >= -1,
                                                   time_arr - self.time < self.approach_rate)]
                                closest_time = np.min(time_arr) if time_arr.size > 0 else self.time
                                closest_index = None
                                closest_dist = None
                                # Note deletion
                                if mouse[1] and not old_mouse[1]:
                                    for i, note in enumerate(self.level.notes.get(closest_time, ())):
                                        p_scale = 1 / self.perspective_scale(progress)
                                        note = (((note[0] - 1) * p_scale) + 1, ((note[1] - 1) * p_scale) + 1)
                                        if abs(note[0] - note_pos[0]) < (0.5 / p_scale) and abs(
                                                note[1] - note_pos[1]) < (0.5 / p_scale):
                                            d = math.sqrt(
                                                (abs(note[0] - note_pos[0]) ** 2) + (abs(note[1] - note_pos[1]) ** 2))
                                            if closest_dist is None or closest_dist > d:
                                                closest_index = i
                                                closest_dist = d
                                    if closest_index is not None:
                                        self.notes_changed = True
                                        self.times_to_display = None
                                        del self.level.notes[int(closest_time)][closest_index]
                                        if len(self.level.notes[int(closest_time)]) == 0:
                                            del self.level.notes[int(closest_time)]
                                        self.changed_since_save = True
                                        self.time_since_last_change = time.time()
                                # Draw the note under the cursor
                                if not self.playing:
                                    np_x = adjust(note_pos[0], self.note_snapping[0])
                                    np_y = adjust(note_pos[1], self.note_snapping[1])
                                    draw_note_pos = (np_x, np_y)
                                    self.draw_note(draw_list, draw_note_pos,
                                                   box, 1.0,
                                                   color=0xffff00, alpha=0x40)
                                    if mouse[0] and not old_mouse[0]:
                                        self.notes_changed = True
                                        self.times_to_display = None
                                        if int(math.ceil(self.time)) in self.level.notes:
                                            self.level.notes[int(math.ceil(self.time))].append(draw_note_pos)
                                        else:
                                            self.level.notes[int(math.ceil(self.time))] = [draw_note_pos]
                                        self.changed_since_save = True
                                        self.time_since_last_change = time.time()
                                    if keys[sdl2.SDLK_s] and spline_window_open:
                                        spline_nodes[int(self.time)] = draw_note_pos
                            else:
                                sdl2.SDL_ShowCursor(True)
                            if (mouse_pos[
                                    1] > y + h + 5 - self.timeline_height or dragging_timeline) and level_was_active and not was_resizing_timeline:
                                if cursor != "resize_ew":
                                    if sdl2_cursor is not None:
                                        sdl2.SDL_FreeCursor(sdl2_cursor)
                                    sdl2_cursor = sdl2.SDL_CreateSystemCursor(sdl2.SDL_SYSTEM_CURSOR_SIZEWE)
                                    sdl2.SDL_SetCursor(sdl2_cursor)
                                cursor = "resize_ew"
                                dragging_timeline = mouse[0] and not self.playing
                                if dragging_timeline:
                                    self.time = (mouse_pos[0] / w * timeline_width) - (self.approach_rate / 2)
                                    if not (keys[sdl2.SDL_SCANCODE_LALT] or keys[
                                            sdl2.SDL_SCANCODE_RALT]) and self.bpm != 0:
                                        self.snap_time()

                            elif cursor == "resize_ew" and sdl2_cursor is not None:
                                sdl2.SDL_FreeCursor(sdl2_cursor)
                                sdl2_cursor = None
                                cursor = "arrow"
                            # Draw cursor
                            if self.cursor and (len(self.level.notes) or self.playtesting):
                                notes = self.level.get_notes()
                                if len(notes):
                                    start = np.min(notes)
                                    end = np.max(notes)
                                if self.playtesting or (end - start):
                                    progress = (self.time - start) / (end - start)
                                    if (cursor_spline is None or self.notes_changed) and not self.playtesting:
                                        nodes = []
                                        for timing, notes in dict(sorted(self.level.notes.items())).items():
                                            node_x, node_y = 0, 0
                                            for x, y in notes:
                                                node_x += x / len(notes)
                                                node_y += y / len(notes)
                                            nodes.append((timing, node_x, node_y))
                                        nodes = np.array(nodes, dtype=np.float64)
                                        cursor_spline = CubicSpline(nodes[:, 0], nodes[:, 1:])

                                    if self.playtesting:
                                        cursor_positions = [cursor_pos] + cursor_positions[
                                            :6]  # NOTE: using a .insert breaks because of None
                                    else:
                                        cursor_positions = [cursor_spline(self.time - t) for t in
                                                            range(0, 75, 1)]
                                    self.camera_pos = ((cursor_positions[0][0] - 1) * self.parallax,
                                                       (cursor_positions[0][1] - 1) * self.parallax)

                                    def position(pos):
                                        return self.note_pos_to_abs_pos(pos, box, 1)

                                    draw_list.add_circle_filled(*position(cursor_positions[0]),
                                                                (square_side / self.vis_map_size) / 20,
                                                                get_time_color() if easter_egg_active else 0xFFFFFFFF,
                                                                num_segments=32)
                                else:
                                    self.camera_pos = (0, 0)
                                    cursor_positions = []
                                draw_list.add_polyline([position(p) for p in cursor_positions],
                                                       get_time_color() & 0x40FFFFFF if easter_egg_active else 0x40FFFFFF,
                                                       thickness=(square_side / self.vis_map_size) / 20)
                            # Draw current statistics
                            if not self.preview_mode:
                                fps_text = f"{int(self.io.framerate)}{f'/{self.fps_cap}' if not self.vsync else ''} FPS"
                                fps_size = imgui.calc_text_size(fps_text)
                                draw_list.add_text(w - fps_size.x - 4, y + 2, 0x80FFFFFF, fps_text)
                                if not self.preview_mode:
                                    for rect in timeline_rects:
                                        rect.draw(draw_list)
                                        self.rects_drawn += 1
                                rdtf_size = imgui.calc_text_size(f"{self.rects_drawn} rects drawn")
                                draw_list.add_text(w - rdtf_size.x - 4, y + fps_size.y + 2, 0x80FFFFFF,
                                                   f"{self.rects_drawn} rects drawn")
                            self.rects_drawn = 0
                            imgui.end_child()
                        imgui.end()
                    imgui.pop_style_var(imgui.STYLE_WINDOW_PADDING)
                    if self.notes_changed and self.level is not None:
                        self.times_to_display = self.level.get_notes()
                        self.notes_changed = False
                    # Resize the timeline when needed
                    if not self.preview_mode and level_was_active and not dragging_timeline and (
                            abs(((y + h) - mouse_pos[1]) - self.timeline_height) <= 5 or was_resizing_timeline):
                        if cursor != "resize_ns":
                            if sdl2_cursor is not None:
                                sdl2.SDL_FreeCursor(sdl2_cursor)
                            sdl2_cursor = sdl2.SDL_CreateSystemCursor(sdl2.SDL_SYSTEM_CURSOR_SIZENS)
                            sdl2.SDL_SetCursor(sdl2_cursor)
                        cursor = "resize_ns"
                        draw_list.add_rect_filled(x, (y + h - 3) - self.timeline_height, x + w,
                                                  (y + h + 2) - self.timeline_height, 0xffff8040)
                        was_resizing_timeline = False
                        if mouse[0]:
                            was_resizing_timeline = True
                            self.timeline_height = max(5, (y + h) - mouse_pos[1])
                    elif cursor == "resize_ns" and sdl2_cursor is not None:
                        sdl2.SDL_FreeCursor(sdl2_cursor)
                        sdl2_cursor = None
                        cursor = "arrow"
                # Error window
                if self.error is not None:
                    imgui.open_popup("Error!")
                    if imgui.begin_popup_modal("Error!")[0]:
                        imgui.push_font(default_font)
                        tb = "\n".join(traceback.format_exception(self.error)).rstrip("\n")
                        imgui.input_text_multiline("##error", tb, len(tb),
                                                   7 * max([len(line) for line in tb.split("\n")]) + 40,
                                                   imgui.get_text_line_height_with_spacing() * len(tb.split("\n")),
                                                   flags=imgui.INPUT_TEXT_READ_ONLY)
                        imgui.pop_font()
                        if imgui.button("Close"):
                            imgui.close_current_popup()
                            self.error = None
                        imgui.end_popup()
            if easter_egg_activated:
                imgui.push_style_color(imgui.COLOR_BORDER, 0, 0, 0, 0)
                imgui.push_style_color(imgui.COLOR_POPUP_BACKGROUND, 0, 0, 0, 0.5)
                imgui.push_style_var(imgui.STYLE_POPUP_ROUNDING, 0)
                imgui.push_style_color(imgui.COLOR_TEXT, 0, 1, 0, 1)
                imgui.push_style_color(imgui.COLOR_HEADER_ACTIVE, 0, 0, 0, 0)
                imgui.push_style_color(imgui.COLOR_HEADER_HOVERED, 0, 0, 0, 0)
                if imgui.begin_popup("Easter Egg", imgui.WINDOW_NO_TITLE_BAR):
                    imgui.set_window_font_scale(2)
                    imgui.text("[ ACCESS GRANTED ]")
                    imgui.end_popup()
                imgui.pop_style_color(5)
                imgui.pop_style_var(1)
            old_mouse = mouse
            old_keys = keys
            GL.glClearColor(0., 0., 0., 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            imgui.render()
            impl.render(imgui.get_draw_data())
            sdl2.SDL_GL_SwapWindow(window)
            if self.playing:
                self.time = ((time.perf_counter_ns() - self.starting_time) / (
                    1000000 / self.audio_speed)) + self.starting_position
            self.time = min(max(self.time, 0),
                            2 ** 31 - 1)  # NOTE: This needs to be 2**31-1 no matter if it's on a 32-bit or 64-bit computer, so no sys.maxsize here
            was_playing = self.playing
            self.unique_label_counter = 0
            if not self.vsync:
                dt = (time.perf_counter_ns() - dt) / 1000000000
                time.sleep(max((1 / self.fps_cap) - dt, 0))

    def adjust_pos(self, cen, pos, progress):
        visual_size = 1 / (1 + ((1 - progress) * self.approach_distance))
        return (cen * visual_size) + (pos * (1 - visual_size))

    def perspective_scale(self, progress):
        return 1 / (1 + ((1 - progress) * self.approach_distance))

    def note_pos_to_abs_pos(self, note_pos, box, progress):
        note_pos = [note_pos[0] + self.camera_pos[0], note_pos[1] + self.camera_pos[1]]
        center = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        spacing = ((box[2] - box[0]) / self.vis_map_size)
        position = (center[0] + ((note_pos[0] - 1) * spacing),
                    center[1] + ((note_pos[1] - 1) * spacing))
        position = (self.adjust_pos(position[0], center[0], progress),
                    self.adjust_pos(position[1], center[1], progress))
        return position

    def draw_note(self, draw_list, note_pos, box, progress, color=0xFFFFFF, alpha=0xff, size=1.0):
        if progress <= 1:
            spacing = ((box[2] - box[0]) / self.vis_map_size)
            visual_scale = (spacing / 1.25) * self.perspective_scale(progress)
            note_size = visual_scale * size
            position = self.note_pos_to_abs_pos(note_pos, box, progress)
            draw_list.add_rect(position[0] - note_size // 2, position[1] - note_size // 2,
                               position[0] + note_size // 2, position[1] + note_size // 2,
                               (int(alpha * max(progress, 0)) << 24) | color, thickness=max((note_size // 8), 0),
                               rounding=self.rounding * note_size / 2)

            self.rects_drawn += 1

    def saveas(self):
        i = FORMATS.index(self.level.__class__)
        changed, value = self.save_file_dialog({FORMAT_NAMES[i]: FORMAT_EXTS[i]})
        if changed:
            try:
                self.level.save(value, self.bpm, self.offset, self.time_signature, self.swing)
                self.changed_since_save = False
            except Exception as e:
                self.error = e
