"""Reader/writer for the GVAS container used by Persona 3 Reload (UE 4.27).

Layout of a property tag in this save flavour:

    name            FString
    type            FString
    <type specific payload>

Type payloads (``size`` is a single byte holding the byte width of the value
for the numeric kinds; the eight bytes after it are reserved and zero):

    IntProperty      size(1) 0*8 value(i32)
    Int8Property     size(1) 0*8 value(i8)
    Int64Property    size(1) 0*8 value(i64)
    UInt32Property   size(1) 0*8 value(u32)
    UInt16Property   size(1) 0*8 value(u16)
    FloatProperty    size(1) 0*8 value(f32)
    StrProperty      flag(1) 0*8 value(FString)
    NameProperty     flag(1) 0*8 value(FString)
    BoolProperty     0*8 value(u8) 0*1
    EnumProperty     size(u32) 0*4 enum_name(FString) 0*1 value(FString)
    StructProperty   size(u32) 0*4 struct_type(FString) guid(16) 0*1 <props>
    ArrayProperty    size(u32) 0*4 item_type(FString) 0*1 count(u32) <items>
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any


class GvasError(Exception):
    pass


RESERVED = 8  # zero bytes that follow the size byte of scalar properties


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise GvasError(f"unexpected end of data at 0x{self.pos:x} (wanted {n} bytes)")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self) -> int:
        return self.read(1)[0]

    def i8(self) -> int:
        return struct.unpack("<b", self.read(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def i16(self) -> int:
        return struct.unpack("<h", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def string(self) -> str:
        length = self.i32()
        if length == 0:
            return ""
        if length < 0:
            raw = self.read(abs(length) * 2)
            return raw[:-2].decode("utf-16-le", "replace")
        raw = self.read(length)
        return raw[:-1].decode("utf-8", "replace")


class Writer:
    def __init__(self):
        self.parts: list[bytes] = []

    def raw(self, b: bytes) -> None:
        self.parts.append(bytes(b))

    def u8(self, v: int) -> None:
        self.parts.append(struct.pack("<B", v))

    def i8(self, v: int) -> None:
        self.parts.append(struct.pack("<b", v))

    def u16(self, v: int) -> None:
        self.parts.append(struct.pack("<H", v))

    def i16(self, v: int) -> None:
        self.parts.append(struct.pack("<h", v))

    def u32(self, v: int) -> None:
        self.parts.append(struct.pack("<I", v))

    def i32(self, v: int) -> None:
        self.parts.append(struct.pack("<i", v))

    def u64(self, v: int) -> None:
        self.parts.append(struct.pack("<Q", v))

    def i64(self, v: int) -> None:
        self.parts.append(struct.pack("<q", v))

    def f32(self, v: float) -> None:
        self.parts.append(struct.pack("<f", v))

    def f64(self, v: float) -> None:
        self.parts.append(struct.pack("<d", v))

    def zeros(self, n: int) -> None:
        self.parts.append(b"\x00" * n)

    def string(self, s: str, wide: bool | None = None) -> None:
        if s == "":
            self.i32(0)
            return
        if wide is None:
            wide = any(ord(ch) > 0x7F for ch in s)
        if wide:
            encoded = s.encode("utf-16-le")
            self.i32(-(len(encoded) // 2 + 1))
            self.raw(encoded + b"\x00\x00")
        else:
            encoded = s.encode("utf-8")
            self.i32(len(encoded) + 1)
            self.raw(encoded + b"\x00")

    def build(self) -> bytes:
        return b"".join(self.parts)


@dataclass
class Header:
    save_game_version: int = 2
    package_version: int = 522
    engine_version: str = "4.27.2"
    engine_build: int = 0
    engine_branch: str = "++UE4+Release-4.27"
    custom_version_format: int = 3
    custom_versions: list = field(default_factory=list)
    save_game_class_name: str = ""

    @classmethod
    def read(cls, r: Reader) -> "Header":
        if r.read(4) != b"GVAS":
            raise GvasError("not a GVAS file (missing magic)")
        h = cls()
        h.save_game_version = r.i32()
        h.package_version = r.i32()
        if h.save_game_version >= 3:
            h.engine_version = r.string()
            h.engine_build = r.i32()
        else:
            major, minor, patch = r.u16(), r.u16(), r.u16()
            h.engine_build = r.i32()
            h.engine_version = f"{major}.{minor}.{patch}"
        h.engine_branch = r.string()
        h.custom_version_format = r.i32()
        for _ in range(r.i32()):
            h.custom_versions.append((r.read(16), r.i32()))
        h.save_game_class_name = r.string()
        return h

    def write(self, w: Writer) -> None:
        w.raw(b"GVAS")
        w.i32(self.save_game_version)
        w.i32(self.package_version)
        if self.save_game_version >= 3:
            w.string(self.engine_version)
            w.i32(self.engine_build)
        else:
            for part in self.engine_version.split("."):
                w.u16(int(part))
            w.i32(self.engine_build)
        w.string(self.engine_branch)
        w.i32(self.custom_version_format)
        w.i32(len(self.custom_versions))
        for guid, ver in self.custom_versions:
            w.raw(guid)
            w.i32(ver)
        w.string(self.save_game_class_name)


# ---------------------------------------------------------------- properties

@dataclass
class Property:
    name: str
    type: str

    @staticmethod
    def read(r: Reader) -> "Property | None":
        name = r.string()
        if name == "None":
            r.string()
            return None
        ptype = r.string()
        cls = _TYPES.get(ptype)
        if cls is None:
            raise GvasError(f"unsupported property type: {ptype!r} (name={name!r})")
        prop = cls.__new__(cls)
        prop.name = name
        prop.type = ptype
        prop._read(r)
        return prop

    def write(self, w: Writer) -> None:
        w.string(self.name)
        w.string(self.type)
        self._write(w)

    def _read(self, r: Reader) -> None:
        raise NotImplementedError

    def _write(self, w: Writer) -> None:
        raise NotImplementedError


_TYPES: dict[str, type] = {}


def _register(cls: type) -> type:
    _TYPES[cls.__name__.removesuffix("Property").join(["", "Property"])] = cls
    return cls


@dataclass
class IntProperty(Property):
    size: int = 4
    value: int = 0
    index: int = 0

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        self.index = r.u32()
        r.read(1)
        self.value = r.i32()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.u32(self.index)
        w.zeros(1)
        w.i32(self.value)


@dataclass
class Int8Property(Property):
    size: int = 1
    value: int = 0
    index: int = 0

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        self.index = r.u32()
        r.read(1)
        self.value = r.i8()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.u32(self.index)
        w.zeros(1)
        w.i8(self.value)


@dataclass
class Int64Property(Property):
    size: int = 8
    value: int = 0
    index: int = 0

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        self.index = r.u32()
        r.read(1)
        self.value = r.i64()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.u32(self.index)
        w.zeros(1)
        w.i64(self.value)


@dataclass
class UInt32Property(Property):
    size: int = 4
    value: int = 0
    index: int = 0

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        self.index = r.u32()
        r.read(1)
        self.value = r.u32()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.u32(self.index)
        w.zeros(1)
        w.u32(self.value)


@dataclass
class UInt16Property(Property):
    size: int = 2
    value: int = 0
    index: int = 0

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        self.index = r.u32()
        r.read(1)
        self.value = r.u16()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.u32(self.index)
        w.zeros(1)
        w.u16(self.value)


@dataclass
class FloatProperty(Property):
    size: int = 4
    value: float = 0.0
    index: int = 0

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        self.index = r.u32()
        r.read(1)
        self.value = r.f32()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.u32(self.index)
        w.zeros(1)
        w.f32(self.value)


@dataclass
class BoolProperty(Property):
    value: bool = False

    def _read(self, r: Reader) -> None:
        r.read(RESERVED)
        self.value = bool(r.u8())
        r.read(1)

    def _write(self, w: Writer) -> None:
        w.zeros(RESERVED)
        w.u8(1 if self.value else 0)
        w.zeros(1)


@dataclass
class StrProperty(Property):
    flag: int = 0
    value: str = ""

    def _read(self, r: Reader) -> None:
        self.flag = r.u8()
        r.read(RESERVED)
        self.value = r.string()

    def _write(self, w: Writer) -> None:
        w.u8(self.flag)
        w.zeros(RESERVED)
        w.string(self.value)


@dataclass
class NameProperty(Property):
    flag: int = 0
    value: str = ""

    def _read(self, r: Reader) -> None:
        self.flag = r.u8()
        r.read(RESERVED)
        self.value = r.string()

    def _write(self, w: Writer) -> None:
        w.u8(self.flag)
        w.zeros(RESERVED)
        w.string(self.value)


@dataclass
class EnumProperty(Property):
    size: int = 0
    enum_type: str = ""
    value: str = ""

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        r.read(4)
        self.enum_type = r.string()
        r.read(1)
        self.value = r.string()

    def _write(self, w: Writer) -> None:
        w.u32(self.size)
        w.zeros(4)
        w.string(self.enum_type)
        w.zeros(1)
        w.string(self.value)


@dataclass
class StructProperty(Property):
    size: int = 0
    struct_type: str = ""
    guid: bytes = b"\x00" * 16
    inner: list = field(default_factory=list)

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        r.read(4)
        self.struct_type = r.string()
        self.guid = r.read(16)
        r.read(1)
        self.inner: list | bytes = []
        if self.struct_type in ("Guid", "DateTime", "Vector", "Quat", "Rotator", "LinearColor", "Color"):
            self.inner = r.read(self.size)
            return
        end = r.pos + self.size
        while r.pos < end:
            prop = Property.read(r)
            if prop is None:
                break
            self.inner.append(prop)
        r.pos = end

    def _write(self, w: Writer) -> None:
        if isinstance(self.inner, (bytes, bytearray)):
            payload = bytes(self.inner)
        else:
            body = Writer()
            for prop in self.inner:
                prop.write(body)
            body.string("None")
            payload = body.build()
        w.u32(len(payload))
        w.zeros(4)
        w.string(self.struct_type)
        w.raw(self.guid)
        w.zeros(1)
        w.raw(payload)


@dataclass
class ArrayProperty(Property):
    size: int = 0
    item_type: str = ""
    items: list = field(default_factory=list)

    def _read(self, r: Reader) -> None:
        self.size = r.u32()
        r.read(4)
        self.item_type = r.string()
        r.read(1)
        count = r.i32()
        for _ in range(count):
            self.items.append(_read_value(r, self.item_type))

    def _write(self, w: Writer) -> None:
        body = Writer()
        for item in self.items:
            _write_value(body, self.item_type, item)
        payload = body.build()
        w.u32(len(payload))
        w.zeros(4)
        w.string(self.item_type)
        w.zeros(1)
        w.i32(len(self.items))
        w.raw(payload)


def _read_value(r: Reader, item_type: str) -> Any:
    if item_type == "IntProperty":
        return r.i32()
    if item_type == "Int8Property":
        return r.i8()
    if item_type == "Int64Property":
        return r.i64()
    if item_type == "UInt32Property":
        return r.u32()
    if item_type == "UInt16Property":
        return r.u16()
    if item_type == "FloatProperty":
        return r.f32()
    if item_type == "BoolProperty":
        return bool(r.u8())
    if item_type in ("StrProperty", "NameProperty"):
        return r.string()
    raise GvasError(f"unsupported array item type: {item_type!r}")


def _write_value(w: Writer, item_type: str, value: Any) -> None:
    if item_type == "IntProperty":
        w.i32(value)
    elif item_type == "Int8Property":
        w.i8(value)
    elif item_type == "Int64Property":
        w.i64(value)
    elif item_type == "UInt32Property":
        w.u32(value)
    elif item_type == "UInt16Property":
        w.u16(value)
    elif item_type == "FloatProperty":
        w.f32(value)
    elif item_type == "BoolProperty":
        w.u8(1 if value else 0)
    elif item_type in ("StrProperty", "NameProperty"):
        w.string(value)
    else:
        raise GvasError(f"unsupported array item type: {item_type!r}")


for _cls in (IntProperty, Int8Property, Int64Property, UInt32Property,
             UInt16Property, FloatProperty, BoolProperty, StrProperty,
             NameProperty, EnumProperty, StructProperty, ArrayProperty):
    _TYPES[_cls.__name__.removesuffix("Property") + "Property"] = _cls


@dataclass
class SaveFile:
    header: Header
    root: list

    @classmethod
    def loads(cls, data: bytes) -> "SaveFile":
        r = Reader(data)
        header = Header.read(r)
        root: list = []
        while True:
            save = r.pos
            try:
                name = r.string()
            except GvasError:
                break
            if name == "None":
                r.string()
                break
            r.pos = save
            prop = Property.read(r)
            if prop is None:
                break
            root.append(prop)
        return cls(header, root)

    def dumps(self) -> bytes:
        w = Writer()
        self.header.write(w)
        for prop in self.root:
            prop.write(w)
        w.string("None")
        w.zeros(4)
        return w.build()
