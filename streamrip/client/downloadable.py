import asyncio
import base64
import functools
import hashlib
import itertools
import json
import logging
import os
import re
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

import aiofiles
import aiohttp
import m3u8
import requests
from Cryptodome.Cipher import AES, Blowfish
from Cryptodome.Util import Counter

from .. import converter
from ..exceptions import NonStreamableError

logger = logging.getLogger("streamrip")


BLOWFISH_SECRET = "g4el58wc0zvf9na1"


def generate_temp_path(url: str):
    return os.path.join(
        tempfile.gettempdir(),
        f"__streamrip_{hash(url)}_{time.time()}.download",
    )


async def fast_async_download(path, url, headers, callback):
    chunk_size: int = 2**20  # 1 MB

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, allow_redirects=True) as resp:
            resp.raise_for_status()
            async with aiofiles.open(path, "wb") as file:
                async for chunk in resp.content.iter_chunked(chunk_size):
                    await file.write(chunk)
                    callback(len(chunk))


@dataclass(slots=True)
class Downloadable(ABC):
    session: aiohttp.ClientSession
    url: str
    extension: str
    source: str = "Unknown"
    _size_base: Optional[int] = None

    async def download(self, path: str, callback: Callable[[int], Any]):
        await self._download(path, callback)

    async def size(self) -> int:
        if hasattr(self, "_size") and self._size is not None:
            return self._size

        async with self.session.head(self.url) as response:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length", 0)
            self._size = int(content_length)
            return self._size

    @property
    def _size(self):
        return self._size_base

    @_size.setter
    def _size(self, v):
        self._size_base = v

    @abstractmethod
    async def _download(self, path: str, callback: Callable[[int], None]):
        raise NotImplementedError


class DeezerDownloadable(Downloadable):
    is_encrypted = re.compile("/m(?:obile|edia)/")

    def __init__(self, session: aiohttp.ClientSession, info: dict):
        logger.debug("Deezer info for downloadable: %s", info)
        self.session = session
        self.url = info["url"]
        self.source: str = "deezer"
        qualities_available = [
            i for i, size in enumerate(info["quality_to_size"]) if size > 0
        ]
        if len(qualities_available) == 0:
            raise NonStreamableError("Missing download info. Skipping.")
        max_quality_available = max(qualities_available)
        self.quality = min(info["quality"], max_quality_available)
        self._size = info["quality_to_size"][self.quality]
        self.extension = "mp3" if self.quality <= 1 else "flac"
        self.id = str(info["id"])

    async def _download(self, path: str, callback):
        async with self.session.get(self.url, allow_redirects=True) as resp:
            resp.raise_for_status()
            self._size = int(resp.headers.get("Content-Length", 0))
            if self._size < 20000 and not self.url.endswith(".jpg"):
                try:
                    info = await resp.json()
                    raise NonStreamableError(info.get("error", "File not found."))
                except json.JSONDecodeError:
                    raise NonStreamableError("File not found.")

            if self.is_encrypted.search(self.url) is None:
                logger.debug(f"Deezer file at {self.url} not encrypted.")
                await fast_async_download(path, self.url, self.session.headers, callback)
            else:
                blowfish_key = self._generate_blowfish_key(self.id)
                logger.debug(
                    "Deezer file (id %s) at %s is encrypted. Decrypting with %s",
                    self.id, self.url, blowfish_key,
                )
                async with aiofiles.open(path, "wb") as audio:
                    async for chunk in resp.content.iter_chunked(2048):
                        decrypted_chunk = self._decrypt_chunk(blowfish_key, chunk)
                        await audio.write(decrypted_chunk)
                        callback(len(chunk))

    @staticmethod
    def _decrypt_chunk(key, data):
        return Blowfish.new(
            key, Blowfish.MODE_CBC, b"\x00\x01\x02\x03\x04\x05\x06\x07"
        ).decrypt(data)

    @staticmethod
    def _generate_blowfish_key(track_id: str) -> bytes:
        md5_hash = hashlib.md5(track_id.encode()).hexdigest()
        return "".join(
            chr(functools.reduce(lambda x, y: x ^ y, map(ord, t)))
            for t in zip(md5_hash[:16], md5_hash[16:], BLOWFISH_SECRET)
        ).encode()

class SoundcloudDownloadable(Downloadable):
    def __init__(self, session, info: dict):
        self.session = session
        self.file_type = info["type"]
        self.source = "soundcloud"
        self.extension = "mp3" if self.file_type == "mp3" else "flac"
        self.url = info["url"]

    async def _download(self, path, callback):
        downloader = BasicDownloadable(self.session, self.url, self.extension, "soundcloud")
        await downloader.download(path, callback)
        self.size = downloader.size
        if self.file_type == "original":
            engine = converter.FLAC(path)
            await engine.convert(path)
