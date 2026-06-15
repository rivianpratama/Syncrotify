import functools
import os
import json
import re
import shutil
import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL, parse_options
from ytmusicapi import YTMusic

from .metadata import clean_title, get_year
from .tagging import MV_SEPARATOR_VISUAL, Tags, get_cover, get_1x1_cover
import logging

logger = logging.getLogger(__name__)


def get_js_runtime_options():
	runtime = "node"
	deno_path = os.environ.get("SYNCROTIFY_DENO")
	if not deno_path:
		bin_path = os.environ.get("SYNCROTIFY_BIN_PATH")
		if bin_path:
			candidate = Path(bin_path) / ("deno.exe" if os.name == "nt" else "deno")
			if candidate.exists():
				deno_path = str(candidate)
	if deno_path:
		runtime = f"deno:{deno_path}"
	_, _, _, node_opts = parse_options(
		["--js-runtimes", runtime, "--remote-components", "ejs:github"]
	)
	return node_opts


class Dl:
	def __init__(
		self,
		final_path: Path,
		temp_path: Path,
		cookies_location: Path,
		ffmpeg_location: Path,
		ffprobe_location: Path,
		itag: str,

		cover_width: int,
		cover_height: int,
		cover_format: str,
		cover_quality: int,
		template_folder: str,
		template_file: str,
		exclude_tags: str | None,
		truncate: int,
		dump_json: bool = False,
		use_playlist_name: bool = False,
		auth_location: Path = None,
		target_format: str = "m4a",
		embed_lyrics: bool = True,
		**kwargs,
	):

		# Initialize YTMusic with auth if available
		# Note: We must pass 'auth' to constructor for internal authenticated flag to be true
		if auth_location and auth_location.exists():
			try:
				# ytmusicapi expects 'auth' to be a file path if it's a headers file
				self.ytmusic = YTMusic(auth=str(auth_location))
			except Exception as e:
				logger.warning(f"Warning: Failed to load auth headers in Dl: {e}")
				self.ytmusic = YTMusic()
		else:
			self.ytmusic = YTMusic()
		self.final_path = final_path
		self.temp_path = temp_path
		self.cookies_location = cookies_location
		self.ffmpeg_location = ffmpeg_location
		self.ffprobe_location = ffprobe_location
		self.itag = itag
		self.cover_width = cover_width
		self.cover_height = cover_height
		self.cover_format = cover_format
		self.cover_quality = cover_quality
		self.template_folder = template_folder
		self.template_file = template_file
		self.exclude_tags = [i.lower() for i in exclude_tags.split(",")] if exclude_tags is not None else []
		self.truncate = None if truncate is not None and truncate < 4 else truncate

		self.target_format = target_format
		self.embed_lyrics = embed_lyrics

		self.dump_json = dump_json
		self.soundcloud = False
		# Generate node runtime options (fix for yt-dlp 2025+)
		node_opts = get_js_runtime_options()
		# Disable cache to prevent stale playlist data
		self.default_ydl_opts = {
			"progress": True, 
			"quiet": True, 
			"no_warnings": True, 
			"fixup": "never", 
			"cachedir": False,
			"ffmpeg_location": str(self.ffmpeg_location.parent) if self.ffmpeg_location.name != "ffmpeg" else None, # yt-dlp expects folder or None if in path
			**node_opts
		}
		
		# If specific binary provided, ensure yt-dlp finds it.
		# yt-dlp 'ffmpeg_location' option: location of the ffmpeg binary or directory containing ffmpeg.
		if self.ffmpeg_location.is_absolute() or self.ffmpeg_location.exists():
			 self.default_ydl_opts["ffmpeg_location"] = str(self.ffmpeg_location.parent)

			
		self.use_playlist_name = use_playlist_name

	def get_ydl_extract_info(self, url) -> dict:
		node_opts = get_js_runtime_options()
		# Force lazy_playlist to prevent eager extraction
		ydl_opts: dict[str, str | bool] = {
			"quiet": True, 
			"no_warnings": True, 
			"extract_flat": "in_playlist", # strictly extract playlist items as flat entries
			"lazy_playlist": True, # Ensure we don't fetch all pages at once
			**node_opts
		}
		if self.cookies_location is not None:
			ydl_opts["cookiefile"] = str(self.cookies_location)
		
		# Propagate ffmpeg if needed, though extract_info usually doesn't need it unless post-processing happens immediately
		if "ffmpeg_location" in self.default_ydl_opts:
			ydl_opts["ffmpeg_location"] = self.default_ydl_opts["ffmpeg_location"]


		with YoutubeDL(ydl_opts) as ydl:
			# extract_info with download=False returns a dict. 
			# If lazy_playlist=True, 'entries' inside it is a generator.
			info = ydl.extract_info(url, download=False)
			if info is None:
				raise Exception(f"Failed to extract info for {url}")
			return info

	def get_download_queue(self, url):
		url = url.split("&")[0]
		
		# Optimazation: Use ytmusicapi for playlists to avoid yt-dlp's slow scraping and "Redownloading" phase
		if "list=" in url and not "soundcloud" in url:
			try:
				import urllib.parse
				parsed_url = urllib.parse.urlparse(url)
				query_params = urllib.parse.parse_qs(parsed_url.query)
				list_id = query_params.get('list', [None])[0]

				if list_id:
					# Fetch playlist from ytmusicapi
					# limit=None fetches all tracks. This is usually fast (API vs scraping)
					playlist = {}
					if list_id in ["LM", "LL"]:
						# Liked Songs requires specific method
						# get_liked_songs returns a list of tracks directly, not a dict with 'tracks' key
						# UPDATE: It might return a dict in some versions or context.
						tracks = self.ytmusic.get_liked_songs(limit=None)
						
						logger.info(f"DEBUG: get_liked_songs returned type: {type(tracks)}")
						if isinstance(tracks, dict) and "tracks" in tracks:
							tracks = tracks["tracks"]
							logger.info("DEBUG: extracted 'tracks' from dict response")
							
						playlist = {"title": "Liked Songs", "tracks": tracks}
					else:
						# Normal playlist
						playlist = self.ytmusic.get_playlist(list_id, limit=None)
					
					if result_prefix := playlist.get("title"):
						if self.use_playlist_name:
							self.final_path = self.final_path / self.get_sanizated_string(result_prefix, True)
					
					for track in playlist.get("tracks", []):
						# Map ytmusicapi track to yt-dlp entry format
						yield {
							"id": track.get("videoId"),
							"title": track.get("title"),
							"duration": track.get("duration_seconds"),
							"webpage_url": f"https://music.youtube.com/watch?v={track.get('videoId')}",
							# Add any other fields if necessary
						}
					return
			except Exception as e:
				logger.warning(f"ytmusicapi playlist fetch failed, falling back to yt-dlp: {e}")

		# Fallback to yt-dlp for non-playlists or if optimization fails
		ydl_extract_info: dict = self.get_ydl_extract_info(url)
		
		# NOTE: If we iterate 'entries' here, we are consuming the generator.
		# If dump_json is on, it consumes it. We must handle this.
		if self.dump_json:
			pass 

		if "soundcloud" in ydl_extract_info.get("webpage_url", ""):
			if str(self.final_path) == "./YouTube Music":
				self.final_path = Path("./SoundCloud")
			self.soundcloud = True

		# MPREb check might trigger eager load if not careful
		if "MPREb_" in ydl_extract_info.get("webpage_url_basename", ""):
			ydl_extract_info = self.get_ydl_extract_info(ydl_extract_info["url"])

		if "playlist" in ydl_extract_info.get("webpage_url_basename", "") or \
           "playlist" in ydl_extract_info.get("webpage_url", "") or \
           ydl_extract_info.get("_type") == "playlist":
			
			if self.use_playlist_name:
				playlist_name = ydl_extract_info.get("title", "Unknown Playlist")
				self.final_path = self.final_path / self.get_sanizated_string(playlist_name, True)
			
			# Stream entries
			entries = ydl_extract_info.get("entries")
			if entries:
				for entry in entries:
					yield entry
			else:
				# Should not happen if lazy, but if list is empty
				pass

		elif "watch" in ydl_extract_info.get("webpage_url_basename", "") or self.soundcloud:
			yield ydl_extract_info
		else:
			# Fallback for video URL that didn't match regex
			yield ydl_extract_info

	def get_artist(self, artist_list):
		if len(artist_list) == 1:
			return artist_list[0]["name"]
		return ", ".join([i["name"] for i in artist_list][:-1]) + f' & {artist_list[-1]["name"]}'

	def get_ytmusic_watch_playlist(self, video_id):
		if self.soundcloud:
			return None
		ytmusic_watch_playlist = self.ytmusic.get_watch_playlist(video_id)
		if ytmusic_watch_playlist is None or isinstance(ytmusic_watch_playlist, str):
			raise Exception(f"Track is not available (None or string) {video_id}")
		
		if not ytmusic_watch_playlist["tracks"][0]["length"] and ytmusic_watch_playlist["tracks"][0].get("album"): # type: ignore
			raise Exception(f"Track is not available {video_id}")
		if not ytmusic_watch_playlist["tracks"][0].get("album"): # type: ignore
			return None
		return ytmusic_watch_playlist

	def search_track(self, title):
		return self.ytmusic.search(title, "songs")[0]["videoId"]

	@functools.lru_cache
	def get_ytmusic_album(self, browse_id):
		return self.ytmusic.get_album(browse_id)

	def get_tags(self, ytmusic_watch_playlist, track: dict[str, str | int]) -> Tags:
		# Always collect fresh tags
		return self.__collect_tags(ytmusic_watch_playlist, track)
		
	def __collect_tags(self, ytmusic_watch_playlist, track: dict[str, str | int]):
		"""collects tag information"""
		video_id = ytmusic_watch_playlist["tracks"][0]["videoId"]
		ytmusic_album: dict = self.ytmusic.get_album(ytmusic_watch_playlist["tracks"][0]["album"]["id"])
		_year, _date = get_year(track, ytmusic_album)
		tags: Tags = {
			"title": clean_title(ytmusic_watch_playlist["tracks"][0]["title"]),
			"album": ytmusic_album["title"],
			"albumartist": self.get_artist(ytmusic_album["artists"]),
			"artist": self.get_artist(ytmusic_watch_playlist["tracks"][0]["artists"]),
			"comments": video_id,
			"track": 1,
			"tracktotal": ytmusic_album["trackCount"],
			"date": _date,
			"year": _year,
			"cover_url": f'{ytmusic_watch_playlist["tracks"][0]["thumbnail"][0]["url"].split("=")[0]}'
			+ f'=w{self.cover_width}-h{self.cover_height}-l{self.cover_quality}-{"rj" if self.cover_format == "jpg" else "rp"}'
		}

		# Efficient Track Number Lookup
		if "tracks" in ytmusic_album:
			for i, t in enumerate(ytmusic_album["tracks"]):
				if t.get("videoId") == video_id:
					tags["track"] = i + 1
					break
		
		# Fetch Lyrics if enabled
		if self.embed_lyrics and ytmusic_watch_playlist.get("lyrics"):
			try:
				lyrics_data = self.ytmusic.get_lyrics(ytmusic_watch_playlist["lyrics"])
				if lyrics_data and "lyrics" in lyrics_data:
					tags["lyrics"] = lyrics_data["lyrics"]
			except Exception as e:
				logger.warning(f"Failed to fetch lyrics: {e}")
			
		return tags

	def get_sanizated_string(self, dirty_string, is_folder):
		dirty_string = re.sub(r'[\\/:*?"<>|;]', "_", dirty_string)
		if is_folder:
			dirty_string = dirty_string[: self.truncate]
			if dirty_string.endswith("."):
				dirty_string = dirty_string[:-1] + "_"
		else:
			if self.truncate is not None:
				if self.truncate < 4: self.truncate = 60 # Safety
				dirty_string = dirty_string[: self.truncate - 4]
		return dirty_string.strip()

	def get_temp_location(self, song_id):
		if self.soundcloud:
			return self.temp_path / f"{song_id}.mp3"
		# Temp location depends on what yt-dlp downloaded. 
		# Usually checking folder is better but for now assume m4a/mp4/webm
		return self.temp_path / f"{song_id}.m4a"

	def get_fixed_location(self, song_id):
		ext = f".{self.target_format}"
		return self.temp_path / f"{song_id}_fixed{ext}"

	def get_final_location(self, tags, extension = ".m4a", is_single = False, single_folders = False):
		# Override extension with target format
		extension = f".{self.target_format}"
		
		final_location_folder = self.template_folder.split("/")
		final_location_file = self.template_file.split("/")

		if is_single and not single_folders and self.template_folder.endswith("/{album}"):
			folder = self.template_folder[:-8]
			if len(folder.strip()) == 0:
				folder = "./"
			final_location_folder = folder.split("/")
			if (self.template_file.startswith("{track:02d} ")):
				locfile = self.template_file[12:]
				final_location_file = "{title}".split("/") if locfile.strip() == "" else locfile.split("/")
		
		filename_safe_tags: dict[str, str] = {}
		for k, v in tags.items(): 
			if isinstance(v, list):
				filename_safe_tags[k] = MV_SEPARATOR_VISUAL.join([ vv if isinstance(vv, str) else vv.decode("utf-8") for vv in v ])
			else:
				filename_safe_tags[k] = v
		final_location_folder = [self.get_sanizated_string(i.format(**filename_safe_tags), True) for i in final_location_folder]
		# Handle empty lists to prevent index errors
		if not final_location_file: final_location_file = ["{title}"]
		
		final_location_file = [self.get_sanizated_string(i.format(**filename_safe_tags), True) for i in final_location_file[:-1]] + [
			self.get_sanizated_string(final_location_file[-1].format(**filename_safe_tags), False) + extension
		]
		return self.final_path.joinpath(*final_location_folder).joinpath(*final_location_file)

	def get_cover_location(self, final_location):
		return final_location.parent / f"Cover.{self.cover_format}"

	def download(self, video_id, temp_location):
		temp_base = temp_location.with_suffix("")
		ydl_opts = {
			**self.default_ydl_opts,
			"format": self.itag,
			"outtmpl": str(temp_base) + ".%(ext)s",
		}
		if self.cookies_location is not None:
			ydl_opts["cookiefile"] = str(self.cookies_location)
		with YoutubeDL(ydl_opts) as ydl:
			result = ydl.download(["https://music.youtube.com/watch?v=" + video_id])
		if result != 0:
			raise RuntimeError(
				f"yt-dlp failed to download {video_id} with exit code "
				f"{self.normalize_exit_code(result)}"
			)

		actual_files = [
			path
			for path in temp_location.parent.glob(f"{temp_base.name}.*")
			if path.is_file() and path.suffix not in {".part", ".ytdl"}
		]
		if not actual_files:
			raise FileNotFoundError(
				f"yt-dlp reported success but produced no audio file for {video_id}"
			)
		actual_file = max(actual_files, key=lambda path: path.stat().st_mtime_ns)
		if actual_file.resolve() != temp_location.resolve():
			if temp_location.exists():
				temp_location.unlink()
			shutil.move(str(actual_file), str(temp_location))

	def download_souncloud(self, url, temp_location):
		ydl_opts = {**self.default_ydl_opts, "format": "mp3", "outtmpl": str(temp_location)}
		if self.cookies_location is not None:
			ydl_opts["cookiefile"] = str(self.cookies_location)
		with YoutubeDL(ydl_opts) as ydl:
			ydl.download([url])

	def fixup(self, temp_location, fixed_location):
		if not Path(temp_location).is_file():
			raise FileNotFoundError(f"Downloaded audio file is missing: {temp_location}")

		# Determine conversion needs
		input_codec = self.get_audio_codec(temp_location)
		target_fmt = self.target_format
		
		cmd_args = [str(self.ffmpeg_location), "-loglevel", "error", "-y", "-i", str(temp_location)]
		
		# Format Logic
		if target_fmt == "m4a":
			# If codec matches and we are sure, copy. If unknown (None) or different, transcode.
			if input_codec in ["aac", "alac"]:
				cmd_args.extend(["-c", "copy"]) # No transcode needed
			else:
				# Fallback/Transcode (Handles None/Undetermined)
				cmd_args.extend(["-c:a", "aac", "-b:a", "256k"]) 
			cmd_args.extend(["-f", "mp4"])

		elif target_fmt == "mp3":
			cmd_args.extend(["-c:a", "libmp3lame", "-b:a", "320k", "-f", "mp3"])
			
		elif target_fmt == "opus":
			if input_codec == "opus":
				cmd_args.extend(["-c", "copy"])
			else:
				cmd_args.extend(["-c:a", "libopus", "-b:a", "128k"]) 
			# opus usually in .opus or .ogg container? ffmpeg likes .opus for opus codec
			# cmd_args.extend(["-f", "opus"]) # auto detect from ext

		elif target_fmt == "flac":
			cmd_args.extend(["-c:a", "flac", "-f", "flac"])

		# Startup info for windows
		startupinfo = None
		if os.name == 'nt':
			startupinfo = subprocess.STARTUPINFO()
			startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = subprocess.SW_HIDE

		# Output
		cmd_args.extend(["-movflags", "+faststart", str(fixed_location)])
		
		try:
			subprocess.run(cmd_args, check=True, startupinfo=startupinfo)
		except subprocess.CalledProcessError as e:
			exit_code = self.normalize_exit_code(e.returncode)
			logger.error(f"FFmpeg fixup failed with exit code {exit_code}")
			raise RuntimeError(
				f"FFmpeg fixup failed with exit code {exit_code}"
			) from e

	@staticmethod
	def normalize_exit_code(code):
		if code is not None and code > 0x7fffffff:
			return code - 0x100000000
		return code

	def move_to_final_location(self, fixed_location, final_location):
		final_location.parent.mkdir(parents=True, exist_ok=True)
		shutil.move(fixed_location, final_location)

	def save_cover(self, tags, cover_location):
		fmt = self.cover_format.upper()
		if fmt == "JPG": fmt = "JPEG"
		with open(cover_location, "wb") as f:
			f.write(get_1x1_cover(tags["cover_url"], self.temp_path, "temp_cover", fmt, "auto"))

	def cleanup(self):
		shutil.rmtree(self.temp_path)

	def get_audio_codec(self, file_path):
		"""Use ffprobe to extract the audio codec of the given file."""
		if not Path(file_path).exists():
			logger.error(f"get_audio_codec: File not found: {file_path}")
			return None # Fallback forces transcode

		cmd = [
			str(self.ffprobe_location),
			"-v", "error",
			"-select_streams", "a:0",
			"-show_entries", "stream=codec_name",
			"-of", "json",
			str(file_path)
		]
		startupinfo = None
		if os.name == 'nt':
			startupinfo = subprocess.STARTUPINFO()
			startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = subprocess.SW_HIDE

		try:
			# Run ffprobe and parse output
			result = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo)
			codec_info = json.loads(result.stdout)
			streams = codec_info.get("streams", [])
			if not streams:
				logger.warning(f"get_audio_codec: No audio streams found in {file_path}. result: {codec_info}")
				return None 
			return streams[0]["codec_name"]
		except subprocess.CalledProcessError as e:
			logger.error(f"ffprobe failed for {file_path}. Exit code: {e.returncode}")
			logger.error(f"Stderr: {e.stderr}")
			logger.error(f"Stdout: {e.stdout}")
			return None # Force transcode
		except Exception as e:
			logger.error(f"get_audio_codec error: {e}")
			return None
