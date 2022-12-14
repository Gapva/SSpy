import glob
import json
import os
import struct
import uuid
from abc import ABC, abstractmethod
from io import BytesIO
from itertools import chain
from pathlib import Path
from hashlib import sha1

import numpy as np
from PIL import Image
from pydub import AudioSegment


def read_line(file):
    out = bytearray(b"")
    while (f := file.read(1)) != b"\n":
        out.append(int.from_bytes(f, "little"))
    return out.decode("utf-8")


class Level(ABC):
    def __init__(self,
                 name: str = "Unnamed",
                 authors: list[str] = [],
                 notes: dict[int, list[tuple[int, int]]] = None,
                 cover: Image.Image = None,
                 audio: AudioSegment = None,
                 difficulty: int | str = -1,
                 id: str = None):
        self.id = id if id is not None else str(uuid.uuid1())
        self.name = name
        self.authors = authors
        self.notes = notes if notes is not None else {}
        self.cover = cover
        self.audio = audio
        self.difficulty = difficulty

    def __str__(self):
        return f"{self.__class__.__name__}(author: {self.authors}, cover: {self.cover}, difficulty: {self.difficulty}, id: {self.id}, name: {self.name}, notes: ({len(self.notes)} notes), level_name: {self.level_name})"

    def get_end(self):
        times_to_display = self.get_notes()
        return (np.max(times_to_display) if times_to_display.shape[0] > 0 else 1000)

    def get_notes(self):
        return np.sort(np.array(tuple(self.notes.keys()), dtype=np.int32))

    @classmethod
    @abstractmethod
    def load(cls, file):
        raise NotImplementedError

    @abstractmethod
    def save(self, *_):
        raise NotImplementedError


def write_sspm2_variable(output, var, custom_type, arr_type=None):
    if custom_type == 1:
        output.write(var.to_bytes(1, "little"))
    elif custom_type == 2:
        output.write(var.to_bytes(2, "little"))
    elif custom_type == 3:
        output.write(var.to_bytes(4, "little"))
    elif custom_type == 4:
        output.write(var.to_bytes(8, "little"))
    elif custom_type == 5:
        output.write(struct.pack("f", var))
    elif custom_type == 6:
        output.write(struct.pack("d", var))
    elif custom_type == 7:
        # Position
        output.write(b"\x01")  # eh
        output.write(struct.pack("ff", float(var[0]), float(var[1])))
    elif custom_type == 8:
        output.write(len(var).to_bytes(2, "little"))
        output.write(var)
    elif custom_type == 9:
        wstr(output, var)
    elif custom_type == 10:
        output.write(len(var).to_bytes(4, "little"))
        output.write(var)
    elif custom_type == 11:
        wstr(output, var, 4)
    elif custom_type == 12:
        # Array
        output.write(arr_type.to_bytes(1, "little"))
        output.write(b"\x00" * 4)  # Reserve space for bit len
        arr_start = output.tell()
        output.write(len(var).to_bytes(2, "little"))
        for v in var:
            write_sspm2_variable(output, arr_type, v)
        arr_end = output.tell()
        output.seek(arr_start - 4)
        output.write((arr_end - arr_start).to_bytes(4, "little"))
        output.seek(arr_end)
    else:
        raise Exception(f"Error while saving SSPMv2: Field type {hex(custom_type)} isn't defined!")


def read_sspmv2_variable(f, custom_type=None):
    if custom_type is None:
        custom_type = ord(f.read(1))
    if custom_type == 0:
        return (None, custom_type)
    elif custom_type == 1:
        return ord(f.read(1)), custom_type
    elif custom_type == 2:
        return int.from_bytes(f.read(2), "little"), custom_type
    elif custom_type == 3:
        return int.from_bytes(f.read(4), "little"), custom_type
    elif custom_type == 4:
        return int.from_bytes(f.read(8), "little"), custom_type
    elif custom_type == 5:
        return struct.unpack("f", f.read(4))[0], custom_type
    elif custom_type == 6:
        return struct.unpack("d", f.read(8))[0], custom_type
    elif custom_type == 7:
        # Position
        is_quantum = ord(f.read(1))
        if is_quantum:
            return (struct.unpack("ff", f.read(8))), custom_type
        else:
            return (struct.unpack("BB", f.read(2))), custom_type
    elif custom_type == 8:
        return f.read(int.from_bytes(f.read(2), "little")), custom_type
    elif custom_type == 9:
        return f.read(int.from_bytes(f.read(2), "little")).decode("utf-8"), custom_type
    elif custom_type == 10:
        return f.read(int.from_bytes(f.read(4), "little")), custom_type
    elif custom_type == 11:
        return f.read(int.from_bytes(f.read(4), "little")).decode("utf-8"), custom_type
    elif custom_type == 12:
        # Array
        values = []
        c_type = ord(f.read(1))
        f.read(4)  # array bit length, don't need this
        arr_length = int.from_bytes(f.read(2), "little")
        for _ in arr_length:
            values.append(read_sspmv2_variable(f, c_type)[0])
        return values, custom_type, c_type
    else:
        raise Exception(f"Error while loading SSPMv2: Field type {hex(custom_type)} isn't defined!")


def wstr(output, string, length=2):
    output.write(len(string.encode("utf-8")).to_bytes(length, "little"))
    output.write(string.encode("utf-8"))


class SSPMLevel(Level):
    def __init__(self, *args,
                 custom_fields={
                     "bpm": (120, 6),
                     "time_signature_num": (4, 2),
                     "time_signature_den": (4, 2),
                     "offset": (0, 3),
                     "swing": (0.5, 6)
                 },
                 song_name="Unnamed", marker_types={"ssp_note": [0x7]}, markers=[], modchart=False, rating=0, **kwargs):
        self.song_name = song_name
        self.custom_fields = custom_fields
        self.marker_types = marker_types
        self.markers = markers
        self.modchart = modchart
        self.rating = rating
        super().__init__(*args, **kwargs)

    @classmethod
    def load(cls, file):
        with open(file, "rb") as f:
            assert f.read(
                4) == b"SS+m", "Invalid f signature! Your level might be corrupted, or in the wrong format."
            version = int.from_bytes(f.read(2), "little")
            if version == 1:
                print("Converting map from SSPMv1...")
                f.read(2)  # "Reserved bits aren't 0. Is this a modchart?"
                read_line(f)
                song_name = read_line(f)
                song_author = read_line(f)
                f.read(4)  # MS length, not needed
                note_count = int.from_bytes(f.read(4), "little")
                difficulty = int.from_bytes(f.read(1), "little") - 1
                cover = None
                if f.read(1) == b"\x02":
                    data_length = int.from_bytes(f.read(8), "little")
                    image_data = f.read(data_length)
                    with BytesIO(image_data) as io:
                        with Image.open(io) as im:
                            cover = im.copy()
                audio = None
                if f.read(1) == b"\x01":
                    data_length = int.from_bytes(f.read(8), "little")
                    audio_data = f.read(data_length)
                    with BytesIO(audio_data) as io:
                        audio = AudioSegment.from_file(io).set_sample_width(
                            2)  # HACK: if i don't do this, it plays horribly clipped and way too loud. it's a simpleaudio bug :/
                notes = {}
                for _ in range(note_count):
                    timing = int.from_bytes(f.read(4), "little")
                    if f.read(1) == b"\x00":
                        x = int.from_bytes(f.read(1), "little")
                        y = int.from_bytes(f.read(1), "little")
                    else:
                        x, y = struct.unpack("ff", f.read(8))  # nice
                    if timing in notes:
                        notes[timing].append((x, y))
                    else:
                        notes[timing] = [(x, y)]
                metadata = True
                try:
                    assert f.read(4) == b"SSPy"
                    bpm = struct.unpack("d", f.read(8))[0]
                    offset = int.from_bytes(f.read(4), "little")
                    time_signature = struct.unpack("HH", f.read(4))
                    swing = struct.unpack("d", f.read(8))[0]
                except (EOFError, AssertionError):
                    metadata = False
                return cls(song_name, [song_author], notes, cover, audio, difficulty, None), \
                    (bpm, offset, time_signature, swing) if metadata else None
            elif version == 2:
                assert f.read(4) == b"\x00\x00\x00\x00", "Reserved bits were not 0."
                f.read(20)  # skip past the hash, not needed
                f.read(4)  # ending pos
                f.read(4)  # num of notes
                marker_amt = int.from_bytes(f.read(4), "little")  # num of markers
                difficulty = int.from_bytes(f.read(1), "little") - 1
                rating = int.from_bytes(f.read(2), "little")
                has_audio = bool(ord(f.read(1)))
                has_cover = bool(ord(f.read(1)))
                modchart = bool(ord(f.read(1)))  # is modchart?
                f.read(24)  # custom data offset/len and audio offset, dont need
                audio_bitlen = int.from_bytes(f.read(8), "little")
                f.read(8)  # cover offset, again don't need
                cover_bitlen = int.from_bytes(f.read(8), "little")
                f.read(32)
                song_id = f.read(int.from_bytes(f.read(2), "little")).decode("utf-8")
                name = f.read(int.from_bytes(f.read(2), "little")).decode("utf-8")
                song_name = f.read(int.from_bytes(f.read(2), "little")).decode("utf-8")
                authors = []
                for _ in range(int.from_bytes(f.read(2), "little")):
                    authors.append(f.read(int.from_bytes(f.read(2), "little")).decode("utf-8"))
                fields = {}
                for _ in range(int.from_bytes(f.read(2), "little")):
                    custom_id = f.read(int.from_bytes(f.read(2), "little")).decode("utf-8")
                    value, f_type = read_sspmv2_variable(f)
                    fields[custom_id] = (value, f_type)
                metadata = False
                if "bpm" in fields and "offset" in fields and "time_signature_num" in fields and "time_signature_den" in fields and "swing" in fields:
                    metadata = True
                    bpm = fields["bpm"][0]
                    offset = fields["offset"][0]
                    time_signature = [fields["time_signature_num"][0], fields["time_signature_den"][0]]
                    swing = fields["swing"][0]
                audio = None
                if has_audio:
                    with BytesIO(f.read(audio_bitlen)) as buf:
                        audio = AudioSegment.from_file(buf).set_sample_width(2)
                cover = None
                if has_cover:
                    with BytesIO(f.read(cover_bitlen)) as buf:
                        with Image.open(buf) as im:
                            cover = im.copy()
                marker_types = {}
                for i in range(ord(f.read(1))):
                    # Each marker is a pseudo-struct
                    marker_id = f.read(int.from_bytes(f.read(2), "little")).decode("utf-8")
                    marker_types[marker_id] = []
                    assert i != 0 or marker_id == "ssp_note", "Error while loading SSPMv2: First defined marker wasn't a note!"
                    for _ in range(ord(f.read(1))):
                        marker_types[marker_id].append(ord(f.read(1)))
                    f.read(1)
                notes = {}
                markers = []
                for i in range(marker_amt):
                    time = int.from_bytes(f.read(4), "little")
                    m_type = ord(f.read(1))
                    if m_type == 0:
                        if time in notes:
                            notes[time].append(read_sspmv2_variable(f, 7)[0])
                        else:
                            notes[time] = [read_sspmv2_variable(f, 7)[0]]
                    else:
                        marker = {"time": time, "m_type": m_type, "fields": []}
                        for v_type in marker_types[tuple(marker_types.keys())[m_type]]["fields"]:
                            marker["fields"].append(read_sspmv2_variable(f, v_type))
                return cls(name, authors, notes, cover, audio, difficulty, song_id, song_name=song_name,
                           custom_fields=fields, marker_types=marker_types, markers=markers,
                           modchart=modchart, rating=rating), \
                    (bpm, offset, time_signature, swing) if metadata else None
            else:
                raise Exception(f"Unknown version: {version}")

    def save(self, filename, bpm, offset, time_signature, swing):
        with open(filename, "wb+") as output:
            self.custom_fields["bpm"] = bpm, 6
            self.custom_fields["swing"] = swing, 6
            self.custom_fields["time_signature_num"] = time_signature[0], 2
            self.custom_fields["time_signature_den"] = time_signature[1], 2
            self.custom_fields["offset"] = offset, 3
            output.write(b"SS+m\x02\x00\x00\x00\x00\x00")  # File signature, version, reserved space
            output.write(b"\x00" * 20)  # Reserve something for the hash, come back later
            output.write(int(self.get_end()).to_bytes(4, "little"))
            output.write(len(self.notes).to_bytes(4, "little"))
            output.write((len(self.notes) + len(self.markers)).to_bytes(4, "little"))
            output.write((self.difficulty + 1).to_bytes(1, "little"))
            output.write(self.rating.to_bytes(2, "little"))
            output.write((self.audio is not None).to_bytes(1, "little"))  # bool is a subclass of int
            output.write((self.cover is not None).to_bytes(1, "little"))
            output.write(self.modchart.to_bytes(1, "little"))
            cdata_loc = output.tell()
            output.write(b"\x00" * 8)  # Reserve space for custom data len
            output.write(b"\x00" * 8)  # Reserve space for custom data ptr
            audio_loc = output.tell()
            output.write(b"\x00" * 8)  # Reserve space for audio len
            output.write(b"\x00" * 8)  # Reserve space for audio ptr
            cover_loc = output.tell()
            output.write(b"\x00" * 8)  # Reserve space for cover len
            output.write(b"\x00" * 8)  # Reserve space for cover ptr
            mkdef_loc = output.tell()
            output.write(b"\x00" * 8)  # Reserve space for marker definitions len
            output.write(b"\x00" * 8)  # Reserve space for marker definitions ptr
            markr_loc = output.tell()
            output.write(b"\x00" * 8)  # Reserve space for marker len
            output.write(b"\x00" * 8)  # Reserve space for marker ptr
            wstr(output, self.id)
            wstr(output, self.name)
            wstr(output, self.song_name)
            output.write(len(self.authors).to_bytes(2, "little"))
            for author in self.authors:
                wstr(output, author)
            cdata_ptr = output.tell()
            output.write(len(self.custom_fields).to_bytes(2, "little"))
            for field in self.custom_fields:
                wstr(output, field)
                field = self.custom_fields[field]
                field_type = field[1].to_bytes(1, "little")
                output.write(field_type)
                write_sspm2_variable(output, *field)
            cdata_end = output.tell()
            output.seek(cdata_loc)
            output.write(cdata_ptr.to_bytes(8, "little"))
            output.write((cdata_end - cdata_ptr).to_bytes(8, "little"))
            output.seek(cdata_end)
            if self.audio is not None:
                audio_ptr = output.tell()
                with BytesIO() as audio_buf:
                    self.audio.export(audio_buf, "ogg")
                    output.write(audio_buf.getvalue())
                audio_end = output.tell()
                output.seek(audio_loc)
                output.write(audio_ptr.to_bytes(8, "little"))
                output.write((audio_end - audio_ptr).to_bytes(8, "little"))
                output.seek(audio_end)
            if self.cover is not None:
                cover_ptr = output.tell()
                with BytesIO() as cover_buf:
                    self.cover.save(cover_buf, "png")
                    output.write(cover_buf.getvalue())
                cover_end = output.tell()
                output.seek(cover_loc)
                output.write(cover_ptr.to_bytes(8, "little"))
                output.write((cover_end - cover_ptr).to_bytes(8, "little"))
                output.seek(cover_end)
            mkdef_ptr = output.tell()
            output.write(len(self.marker_types).to_bytes(1, "little"))
            for m_type in self.marker_types:
                wstr(output, m_type)
                m_type = self.marker_types[m_type]
                output.write(len(m_type).to_bytes(1, "little"))
                for t in m_type:
                    output.write(t.to_bytes(1, "little"))
                output.write(b"\x00")
            mkdef_end = output.tell()
            output.seek(mkdef_loc)
            output.write(mkdef_ptr.to_bytes(8, "little"))
            output.write((mkdef_end - mkdef_ptr).to_bytes(8, "little"))
            output.seek(mkdef_end)
            markr_ptr = output.tell()
            markers = self.markers.copy()
            for note in self.notes:
                for pos in self.notes[note]:
                    markers.append({"time": note, "m_type": 0, "fields": [pos]})
            for marker in sorted(markers, key=lambda x: x["time"]):
                output.write(int(marker["time"]).to_bytes(4, "little"))
                output.write(marker["m_type"].to_bytes(1, "little"))
                for i, var in enumerate(marker["fields"]):
                    var_type = tuple(self.marker_types.values())[marker["m_type"]][i]
                    write_sspm2_variable(output, var, var_type)
            markr_end = output.tell()
            output.seek(markr_loc)
            output.write(markr_ptr.to_bytes(8, "little"))
            output.write((markr_end - markr_ptr).to_bytes(8, "little"))


class RawDataLevel(Level):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def load(cls, file):
        with open(file) as f:
            notes = {}
            data_string = f.read()
            for note in data_string.split(",")[1:]:
                try:
                    x, y, timing = note.split("|")
                    x, y = float(x), float(y)
                    try:
                        notes[int(timing)].append((x, y))
                    except KeyError:
                        notes[int(timing)] = [(x, y)]
                except ValueError:
                    print(f"/!\\ Invalid note! {note}")
            return cls(notes=notes), None

    def save(self, filename, *_):
        with open(filename, "w+") as f:
            output = []
            for timing, notes in dict(sorted(self.notes.items())).items():
                for note in notes:
                    x = 2 - note[0]
                    y = 2 - note[1]
                    x = int(x) if int(x) == x else x
                    y = int(y) if int(y) == y else y
                    output.append(f"{2 - x}|{2 - y}|{timing}")
            f.write(self.id + "," + ",".join(output))


class VulnusLevel(Level):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def load(cls, file):
        assert Path("meta.json").exists(), "Metadata file not found!"
        with open("meta.json", "r") as meta:
            m_data = json.load(meta)  # Raises json.JSONDecodeError, caught outside
        try:
            assert m_data["_version"] == 1, "Unsupported version!"
            song_name = f'{m_data["_artist"]} - {m_data["_title"]}'
            audio = AudioSegment.from_file(m_data["_music"])
            cover = [Path(name).name for name in glob.glob("./cover*")]
            if len(cover):
                assert len(cover) < 2, "Multiple covers found! (?????)"
                with open(cover[0], "rb") as im:
                    with Image.open(im) as i:
                        cover = i.copy()
            else:
                cover = None
            with open(file, "r") as m:
                level = json.load(m)
            difficulty = level["_name"]
            notes = {}
            for note in level["_notes"]:
                timing = int(note["_time"] * 1000)
                position = (1 - note["_x"], note["_y"] + 1)
                if timing in notes:
                    notes[timing].append(position)
                else:
                    notes[timing] = [position]
            metadata = "_sspy" in m_data
            if metadata:
                bpm = m_data["_sspy"]["bpm"]
                offset = m_data["_sspy"]["offset"]
                time_signature = m_data["_sspy"]["time_signature"]
                swing = m_data["_sspy"]["swing"]
        except KeyError as e:
            raise KeyError(f"Error while loading: JSON key {e} not found!")
        return cls(song_name, m_data["_mappers"], notes, cover, audio, difficulty), (
            bpm, offset, time_signature, swing) if metadata else None

    def save(self, filename, bpm, offset, time_signature, swing):
        if self.audio is not None:
            print("Exporting audio...")
            with open("audio.wav", "wb+") as f:
                self.audio.export(f, format="wav")
        print("Exporting metadata...")
        try:  # Load an existing metadata file
            with open("meta.json", "r") as f:
                metadata = json.load(f)
            metadata["_difficulties"].append(f"{filename}.json")
        except FileNotFoundError:
            metadata = {"_difficulties": [f"{filename}.json"]}
        metadata_temp = {"_artist": (self.name.split(" - "))[0], "_title": (self.name.split(" - "))[1],
                         "_mappers": self.authors, "_music": "audio.wav", "_version": 1, "_sspy": {
            "bpm": bpm,
            "time_signature": time_signature,
            "offset": offset,
            "swing": swing
        }}
        metadata |= metadata_temp
        with open("meta.json", "w+") as m:
            json.dump(metadata, m)
        if self.cover is not None:
            print("Exporting cover...")
            for path in glob.glob("./cover*"):
                os.remove(path)
            self.cover.save("cover.png")
        print("Exporting notes...")
        level = {"_notes": [], "_name": self.difficulty}
        for time in self.notes:
            for note in self.notes[time]:
                level["_notes"].append({"_time": time / 1000, "_x": 1 - note[0], "_y": note[1] - 1})
        with open(f"{filename}", "w+") as level_file:
            json.dump(level, level_file)
