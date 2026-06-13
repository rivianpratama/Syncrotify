import time
import logging
import json
import threading
from datetime import datetime
from pathlib import Path
from .dl import Dl
from .tagging import apply_genre_internal, get_video_id_from_file
from .playlist_maker import PlaylistMaker

class BackgroundMonitor:
    def __init__(self):
        self.config_path = Path.home() / ".syncrotify" / "engine_config.json"
        self.headers_path = Path.home() / ".syncrotify" / "auth" / "headers_auth.json"
        self.cookies_txt_path = Path.home() / ".syncrotify" / "auth" / "cookies.txt"
        self.config = self.load_config()
        self.is_running = False
        self.thread = None
        self.logger = logging.getLogger(__name__)
        self.lock = threading.Lock()
        self.last_run_success = False

    def load_config(self):
        default_config = {
            # Sync Logic
            "interval": 600,
            "smart_stop_threshold": 5,
            "skip_duration_threshold": 2100, # 35m
            "max_retries": 3,
            "playlist_url": "",
            
            # Download
            "download_path": str(Path.home() / "Music" / "Syncrotify"),
            "audio_format": "m4a", # m4a, mp3, opus, flac
            "audio_quality": "best", # best, 256k, 128k, low
            "filename_template": "{artist}-{title}",
            "path_truncate_length": 60,

            "speed_limit": "",
            "collision_strategy": "smart_numbering", # smart_numbering, skip, overwrite
            "max_duplicates": 2,
            "size_check_enabled": True,

            # Metadata
            "cover_width": 320,
            "cover_height": 320,
            "cover_format": "JPEG", # JPEG, PNG, BMP
            "cover_quality": 75,
            "embed_lyrics": False,
            "tag_fields": ["title", "artist", "album", "year", "track", "genre", "albumartist"],
            
            # System
            "auto_start": False, # Registry auto start app
            "auto_sync_on_launch": True, # Auto-start sync loop if manifest exists
            "start_minimized": False,
            
            # Other
            "enable_m3u8": False,
            "playlist_output_path": str(Path.home() / "Music" / "Playlists"),
        }
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                    return {**default_config, **loaded}
            except Exception:
                return default_config
        return default_config

    def save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=4)

    def start_auto_sync(self):
        # Reload config to ensure we have latest settings (interval, playlist_url, etc)
        self.config = self.load_config()
        
        if self.is_running:
            return
        
        # Verify Manifest exists for Auto Sync safety
        dl_path = self.resolve_download_path()
        manifest_path = dl_path / "sync_manifest.json"
        if not manifest_path.exists():
            self.logger.warning("Cannot start Auto Sync: sync_manifest.json not found. Run Full Sync first.")
            return

        self.is_running = True
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.logger.info("Auto Sync Started")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1)
        self.logger.info("Auto Sync Stopped")

    def run_loop(self):
        while self.is_running:
            try:
                final_path = self.resolve_download_path()
                if not final_path.exists():
                    self.logger.warning(f"Download directory inaccessible: {final_path}. Waiting...")
                    while self.is_running and not final_path.exists():
                        time.sleep(5)
                        final_path = self.resolve_download_path()
                    if self.is_running:
                        self.logger.info("Download directory found. Resuming.")

                if not self.is_running:
                    break

                # Auto Sync runs "Smart" (Recent) mode usually
                self.process_playlist(mode="recent")

                # Auto Generate Playlist if enabled
                # We check config again in case it changed during loop sleep
                if self.is_running and self.config.get("enable_m3u8", False):
                    self.run_playlist_generation()

            except Exception as e:
                self.logger.error(f"Error in Auto Sync loop: {e}")
            
            # Sleep step
            ival = self.config.get('interval', 600)
            self.logger.info(f"Sync check finished. Sleeping for {ival}s.")
            for _ in range(ival):
                if not self.is_running:
                    break
                time.sleep(1)

    def resolve_download_path(self):
        p = self.config.get("download_path")
        if not p:
            return Path.home() / "Music" / "Syncrotify"
        return Path(p).resolve()

    def run_playlist_generation(self):
        pl_out = self.config.get("playlist_output_path")
        pl_url = self.config.get("playlist_url")
        dl_path = self.resolve_download_path()
        
        if pl_out and pl_url:
            self.logger.info("Generating M3U8 Playlist...")
            try:
                pm = PlaylistMaker(update_status_callback=lambda msg: self.logger.info(f"[PlaylistGen] {msg}"))
                pm.generate_m3u8(pl_url, dl_path, pl_out)
            except Exception as e:
                self.logger.error(f"Playlist generation failed: {e}")

    def generate_sync_manifest(self, playlist_url, download_path):
        """Creates a manifest file listing all songs and config."""
        manifest = {
            "playlist_url": playlist_url,
            "download_path": str(download_path),
            "last_full_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sync_version": "1.0"
        }
        manifest_path = download_path / "sync_manifest.json"
        try:
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=4)
            self.logger.info(f"Created sync_manifest.json at {download_path}")
        except Exception as e:
            self.logger.error(f"Failed to create sync manifest: {e}")

    def check_track_exists(self, final_loc: Path, video_id: str) -> bool:
        if not final_loc.exists():
            return False
        try:
            existing_id = get_video_id_from_file(final_loc)
            if existing_id == video_id:
                return True
            else:
                self.logger.info(f"Collision detected: {final_loc.name} exists but ID {existing_id} != {video_id}")
                return False
        except Exception as e:
            self.logger.warning(f"Failed to verify ID in {final_loc}: {e}")
            return False

    def log_failure(self, final_path: Path, video_id: str, title: str, error: str, playlist_url: str):
        try:
            log_file = final_path / "failed_downloads.txt"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] Playlist: {playlist_url} | Failed: {title} ({video_id}) | Error: {error}\n")
        except Exception as e:
            self.logger.error(f"Failed to write to failure log: {e}")

    def get_collision_free_path(self, final_loc: Path, video_id: str) -> Path | None:
        if not final_loc.exists():
            return final_loc
        if self.check_track_exists(final_loc, video_id):
             return final_loc 
        i = 2
        MAX_DUPLICATES = self.config.get("max_duplicates", 2)
        while i <= MAX_DUPLICATES:
            new_stem = f"{final_loc.stem} ({i})"
            new_loc = final_loc.with_name(f"{new_stem}{final_loc.suffix}")
            if not new_loc.exists():
                return new_loc
            if self.check_track_exists(new_loc, video_id):
                return new_loc
            i += 1
        return None

    def resolve_binary(self, name):
        import sys
        import os

        configured_bin = os.environ.get("SYNCROTIFY_BIN_PATH")
        if configured_bin:
            candidate = Path(configured_bin) / (
                f"{name}.exe" if os.name == "nt" else name
            )
            if candidate.exists():
                return candidate
        
        # Check if frozen (bundled exe)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
            
            # Check root (same dir as exe)
            path = Path(base_dir) / f"{name}.exe"
            if path.exists(): return path
            
            # Check _internal (PyInstaller 6+ default)
            path = Path(base_dir) / "_internal" / f"{name}.exe"
            if path.exists(): return path
            
            # Check MEIPASS (for OneFile mode compatibility)
            if hasattr(sys, '_MEIPASS'):
                 path = Path(sys._MEIPASS) / f"{name}.exe"
                 if path.exists(): return path
        
        # Default/PATH fallback
        return Path(name)

    def process_playlist(self, mode="recent"):
        """
        mode: 'recent' (was Smart - Stop on existing) or 'full' (Check all)
        """
        playlist_url = self.config.get("playlist_url")
        self.last_run_success = False
        if not playlist_url:
            self.logger.warning("No playlist URL configured.")
            return

        if not self.lock.acquire(blocking=False):
             self.logger.warning(f"Sync ({mode}) already in progress. Skipping.")
             return

        try:
            run_had_errors = False
            self.logger.info(f"Starting {mode.title()} Sync: {playlist_url}")
            
            final_path = self.resolve_download_path()
            try:
                final_path.mkdir(parents=True, exist_ok=True)
                if mode == "full":
                    self.generate_sync_manifest(playlist_url, final_path)

                temp_path = final_path / "temp"
                temp_path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.logger.critical(f"Failed to access/create download directory: {final_path}. Check if drive is connected. Error: {e}")
                return
            
            # Config Mappings
            quality_map = {
                "best": "bestaudio/best",
                "256k": "bestaudio[abr<=256]/bestaudio/best",
                "128k": "bestaudio[abr<=128]/bestaudio/best",
                "low": "worstaudio/worst"
            }
            itag_val = quality_map.get(self.config.get("audio_quality", "best"), "bestaudio/best")
            
            # Format handling (m4a default)
            fmt = self.config.get("audio_format", "m4a")
            if fmt == "m4a":
                itag_val = f"bestaudio[ext=m4a]/{itag_val}"
            
            # Resolve Binaries
            ffmpeg_path = self.resolve_binary("ffmpeg")
            ffprobe_path = self.resolve_binary("ffprobe")
            
            dl = Dl(
                final_path=final_path,
                temp_path=temp_path,
                cookies_location=self.cookies_txt_path if self.cookies_txt_path.exists() else None,
                ffmpeg_location=ffmpeg_path,
                ffprobe_location=ffprobe_path,
                itag=itag_val,
                cover_width=self.config.get("cover_width", 320),
                cover_height=self.config.get("cover_height", 320),
                cover_format=self.config.get("cover_format", "JPEG"),
                cover_quality=self.config.get("cover_quality", 94),
                template_folder="",
                template_file=self.config.get("filename_template", "{artist}-{title}"),
                exclude_tags=None, # We will use tag_fields whitelist instead soon, or keep verify logic
                truncate=self.config.get("path_truncate_length", 60),
                dump_json=False,
                use_playlist_name=False,
                auth_location=self.headers_path if self.headers_path.exists() else None,

                target_format=fmt,
                embed_lyrics=self.config.get("embed_lyrics", True)
            )

            try:
                queue = list(dl.get_download_queue(playlist_url))
                if not queue:
                    raise RuntimeError("The source playlist returned no tracks; refusing to continue.")
                
                # Order Logic
                is_liked = "list=LM" in playlist_url or "list=LL" in playlist_url
                scan_queue = []
                if is_liked:
                    self.logger.info("Liked Playlist detected. Processing Top-Down (Newest First).")
                    if queue: scan_queue.extend(queue)
                else:
                    self.logger.info("Normal Playlist detected. Processing Bottom-Up (Reversed).")
                    if queue: scan_queue.extend(reversed(queue))
                
                processed_vids = set()
                consecutive_matches = 0
                max_consecutive_threshold = self.config.get("smart_stop_threshold", 5)

                for i, track in enumerate(scan_queue):
                    if not self.is_running and mode == "auto": 
                         pass
                    
                    vid = track.get("id")
                    if vid in processed_vids: continue
                    processed_vids.add(vid)

                    title = track.get("title", "Unknown")
                    duration = track.get("duration")
                    max_dur = self.config.get("skip_duration_threshold", 2100)
                    if duration and duration > max_dur:
                            self.logger.info(f"Skipping {title} (Duration: {duration}s > {max_dur}s)")
                            continue

                    self.logger.info(f"Checking {title} ({i+1}/{len(scan_queue)})...")

                    MAX_RETRIES = self.config.get("max_retries", 3)
                    for attempt in range(MAX_RETRIES + 1):
                        try:
                            # 1. Fetch Metadata (reused/fetched)
                            q_track = track
                            # ... (Logic mostly same as before, simplified for brevity in this thought trace but I need to write full code)
                            
                            # RE-IMPLEMENT FULL LOGIC from previous background.py to avoid regression
                            # I will paste the core logic back carefully.
                            
                            ytmusic_watch_playlist = dl.get_ytmusic_watch_playlist(vid)
                            if ytmusic_watch_playlist is None:
                                tag_track = dl.get_ydl_extract_info(f"https://www.youtube.com/watch?v={vid}")
                                from .metadata import smart_metadata, TIGER_SINGLE
                                tags = smart_metadata(tag_track, temp_path, "JPEG", "auto")
                                is_single = tags.get("comments") == TIGER_SINGLE
                            else:
                                tags = dl.get_tags(ytmusic_watch_playlist, q_track)
                                is_single = tags["tracktotal"] == 1
                                
                            from .musicbrainz import musicbrainz_enrich_tags
                            tags = musicbrainz_enrich_tags(tags, dl.soundcloud, dl.exclude_tags)
                            tags["comments"] = vid
                            
                            target_path = dl.get_final_location(tags, fmt, is_single, False)
                            
                            strategy = self.config.get("collision_strategy", "smart_numbering")
                            
                            if target_path.exists():
                                existing_id = self.check_track_exists(target_path, vid)
                                
                                # CASE 1: ID Match (Identical Song)
                                if existing_id:
                                    if strategy == "overwrite":
                                        self.logger.info(f"Overwriting existing file: {target_path.name}")
                                        target_path.unlink()
                                    else:
                                        self.logger.info(f"Identical File Found: {target_path.name}")
                                        if mode == "recent":
                                            consecutive_matches += 1
                                            if consecutive_matches >= max_consecutive_threshold:
                                                self.logger.info("Sync Recent: Up to date. Stopping.")
                                                raise StopIteration("Smart Stop")
                                            break
                                        else:
                                            # Full Mode - just skip
                                            break
                                
                                # CASE 2: ID Mismatch (Collision)
                                else:
                                    if strategy == "overwrite":
                                        self.logger.info(f"Collision (Overwrite): Deleting {target_path.name}")
                                        target_path.unlink()
                                        
                                    elif strategy == "skip":
                                        self.logger.info(f"Collision (Skip): Skipping {title} due to existing filename.")
                                        break
                                        
                                    else: # smart_numbering
                                        # Size Check Optimization
                                        if self.config.get("size_check_enabled", True):
                                            # We need temp download to compare size? No, that defeats the purpose of "fast check".
                                            # Actually, without downloading we can't know the new file size.
                                            # The user request implies checking size *after* downloading to temp?
                                            # "Skip if file size matches exactly" usually implies we have the candidates.
                                            # Let's check the logic from previous session: it downloaded to temp first.
                                            # To be efficient, we only do size check if we download to temp first.
                                            pass 

                                        # Proceed to download to temp first to verify collision vs duplicate content
                                        pass 
                           
                            # Download Logic (New or Overwrite or Smart Numbering Candidate)
                            consecutive_matches = 0
                            self.logger.info(f"Downloading {title}")
                            
                            temp_loc = dl.get_temp_location(vid)
                            fixed_loc = dl.get_fixed_location(vid)
                            
                            try:
                                dl.download(vid, temp_loc)
                                dl.fixup(temp_loc, fixed_loc)
                                from .tagging import metadata_applier
                                metadata_applier(tags, fixed_loc, dl.exclude_tags)
                                
                                # Collision Handling with physical file
                                if target_path.exists():
                                    # It might exist if we are in smart_numbering mode and didn't delete it
                                    # Check size now
                                    if self.config.get("size_check_enabled", True):
                                        if fixed_loc.stat().st_size == target_path.stat().st_size:
                                            self.logger.info(f"Identical File Size: {target_path.name}. Skipping.")
                                            if mode == "recent":
                                                consecutive_matches += 1
                                                if consecutive_matches >= max_consecutive_threshold:
                                                     raise StopIteration("Smart Stop")
                                            break

                                    # Get free path
                                    target_path = self.get_collision_free_path(target_path, vid)
                                    if target_path is None:
                                        self.logger.info(f"Duplicate limit reached. Skipping {title}.")
                                        break

                                dl.move_to_final_location(fixed_loc, target_path)
                                apply_genre_internal(target_path)
                                
                            finally:
                                if temp_loc.exists(): temp_loc.unlink() 
                                if fixed_loc.exists(): fixed_loc.unlink()
                            
                            break # Success

                        except StopIteration:
                            raise
                        except Exception as e:
                            # Retry Logic
                            is_conn_err = "Connection" in str(e) or "10054" in str(e)
                            is_perm_err = "WinError 32" in str(e) or isinstance(e, PermissionError)
                            if (is_conn_err or is_perm_err) and attempt < MAX_RETRIES:
                                time.sleep(5 if is_perm_err else 3)
                                continue
                            self.logger.error(f"Failed {title}: {e}")
                            self.log_failure(final_path, vid, title, str(e), playlist_url)
                            run_had_errors = True
                            break

            except StopIteration:
                 self.logger.info("Sync finished (Up to date).")
            except Exception as e:
                self.logger.error(f"Sync Process Failed: {e}")
                run_had_errors = True
            finally:
                import shutil
                if temp_path.exists(): 
                     for _ in range(3):
                         try:
                             shutil.rmtree(temp_path)
                             break
                         except OSError:
                             time.sleep(1)
                         except Exception: break
                self.last_run_success = not run_had_errors
                
                # If Full Sync, maybe cleanup manifest or nothing
                # If Enable M3U8, generate at end of one-off checks too?
        finally:
            self.lock.release()

    def run_sync_with_playlist(self, mode="recent"):
        """Wrapper to run sync then generate playlist if enabled."""
        self.process_playlist(mode)
        
        # Reload config to check for realtime updates to 'enable_m3u8'
        # (Though self.config is usually live reference if modified in GUI? 
        #  GUI modifies self.monitor.config directly, so yes it is live.)
        if self.config.get("enable_m3u8", False):
            self.run_playlist_generation()

    def run_sync_recent(self):
        threading.Thread(target=self.run_sync_with_playlist, args=("recent",), daemon=True).start()

    def run_full_sync(self):
        threading.Thread(target=self.run_sync_with_playlist, args=("full",), daemon=True).start()
