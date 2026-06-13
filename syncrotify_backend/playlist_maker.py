import logging
import os
from pathlib import Path
import ytmusicapi
import threading
from .tagging import get_video_id_from_file

class PlaylistMaker:
    def __init__(self, update_status_callback=None):
        self.update_status = update_status_callback
        self.stop_event = threading.Event()

    def log(self, message):
        if self.update_status:
            self.update_status(message)
        logging.info(f"[PlaylistMaker] {message}")

    def get_auth_headers_path(self):
        return Path.home() / ".syncrotify" / "auth" / "headers_auth.json"

    def authenticate(self):
        headers_path = self.get_auth_headers_path()
        if headers_path.exists():
            self.log("Authenticated with headers_auth.json")
            return ytmusicapi.YTMusic(str(headers_path))
        else:
            self.log("No authentication found, using public access")
            return ytmusicapi.YTMusic()

    def scan_music_dir(self, music_dir: Path):
        """
        Scans the music directory for audio files and maps them by Video ID and Filename.
        """
        self.log(f"Scanning library at: {music_dir} ...")
        
        id_map = {} # video_id -> path (relative to drive root)
        filename_map = {} # filename -> path (relative to drive root)
        
        count = 0
        music_dir = Path(music_dir)
        
        # We need the drive root for Rockbox absolute paths, e.g. /Music/Song.m4a
        # On Windows, music_dir might be F:\Music. Drive root is F:\.
        # Path.absolute() gives F:\Music.
        # We want to store paths starting with /, relative to the drive.
        
        try:
            drive_root = Path(music_dir.anchor)
        except Exception as e:
            self.log(f"Error determining drive root: {e}")
            return {}, {}

        for root, _, files in os.walk(music_dir):
            if self.stop_event.is_set():
                break
                
            for file in files:
                if file.lower().endswith(('.m4a', '.mp3', '.flac', '.opus', '.ogg', '.wav')):
                    full_path = Path(root) / file
                    
                    try:
                        # Create root-relative path (e.g., /Music/Artist/Song.m4a)
                        # internal path handling in python usually strips the drive letter when doing relative_to(drive_root)?
                        # actually relative_to('F:\\') gives 'Music\Song.m4a'
                        # We need to prepend '/' and convert backslashes to slashes.
                        
                        rel_path_obj = full_path.relative_to(drive_root)
                        rockbox_path = "/" + rel_path_obj.as_posix()
                        
                        # Store by filename
                        filename_map[file] = rockbox_path
                        
                        # Store by Video ID from metadata
                        vid = get_video_id_from_file(full_path)
                        if vid:
                            id_map[vid] = rockbox_path
                            
                        count += 1
                        if count % 100 == 0:
                            self.log(f"Scanned {count} files...")
                            
                    except Exception as e:
                        logging.debug(f"Error processing file {file}: {e}")
                        
        self.log(f"Scan complete. Found {count} files.")
        return id_map, filename_map

    def generate_m3u8(self, playlist_url, music_dir, playlist_dir):
        self.stop_event.clear()
        
        try:
            yt = self.authenticate()
            
            # Extract playlist ID
            try:
                if "list=" in playlist_url:
                    playlist_id = playlist_url.split("list=")[1].split("&")[0]
                else:
                    playlist_id = playlist_url
            except IndexError:
                self.log("Invalid Playlist URL")
                return

            self.log(f"Fetching playlist info for ID: {playlist_id}")
            
            tracks = []
            playlist_title = "Playlist"

            try:
                # Special handling for Liked Songs (LM) and Liked Videos (LL - often confused)
                if playlist_id in ["LM", "LL"]:
                     self.log("Detected Liked Songs/Videos. Fetching Liked Songs...")
                     playlist_info = yt.get_liked_songs(limit=None)
                     playlist_title = "Liked Songs"
                     tracks = playlist_info.get('tracks', [])
                else:
                    playlist_info = yt.get_playlist(playlist_id, limit=None)
                    playlist_title = playlist_info.get('title', 'Playlist')
                    tracks = playlist_info.get('tracks', [])
            except Exception as e:
                self.log(f"Failed to fetch playlist: {e}")
                return
            
            if not tracks:
                self.log("Playlist is empty or could not fetch tracks.")
                return

            self.log(f"Found {len(tracks)} tracks in playlist '{playlist_title}'")

            # Scan local files
            id_map, filename_map = self.scan_music_dir(music_dir)
            if self.stop_event.is_set():
               self.log("Operation cancelled.")
               return

            m3u8_content = []
            
            found_count = 0
            missing_count = 0
            
            self.log("Matching tracks...")
            
            for track in tracks:
                if self.stop_event.is_set():
                    break
                    
                video_id = track.get('videoId')
                title = track.get('title', 'Unknown Title')
                artists = track.get('artists', [])
                artist_name = artists[0]['name'] if artists else "Unknown Artist"
                
                matched_path = None
                
                # Try matching by ID first
                if video_id and video_id in id_map:
                    matched_path = id_map[video_id]
                
                # Fallback: Try matching by approximate filename
                if not matched_path:
                    # Heuristic Matching: Artist + Title in filename
                    # Normalize strings: remove non-alphanumeric, lowercase
                    def normalize(s):
                        return "".join(c.lower() for c in s if c.isalnum())

                    norm_title = normalize(title)
                    norm_artist = normalize(artist_name)
                    
                    # Try exact filename construction first (fast)
                    potential_name = f"{artist_name} - {title}.m4a".replace("/", "")
                    if potential_name in filename_map:
                         matched_path = filename_map[potential_name]
                    
                    # If strictly constructed name failed, try fuzzy search
                    if not matched_path:
                        for fname, fpath in filename_map.items():
                            norm_fname = normalize(fname)
                            # Check if both Artist and Title are present in the filename
                            # (ignoring extension for safety, though included in norm_fname)
                            if norm_title in norm_fname and norm_artist in norm_fname:
                                matched_path = fpath
                                break # Take the first reasonable match

                if matched_path:
                    m3u8_content.append(matched_path)
                    found_count += 1
                else:
                    missing_count += 1
                    logging.debug(f"Missing: {artist_name} - {title} ({video_id})")

            if self.stop_event.is_set():
               self.log("Operation cancelled.")
               return

            # Write file
            safe_title = "".join(c for c in playlist_title if c.isalnum() or c in (' ', '-', '_')).strip()
            out_file = Path(playlist_dir) / f"{safe_title}.m3u8"
            
            self.log(f"Writing playlist to {out_file}...")
            
            # Use utf-8-sig for better compatibility with legacy players handling CJK
            with open(out_file, 'w', encoding='utf-8-sig') as f:
                f.write("\n".join(m3u8_content))
                
            self.log(f"Done! Created '{safe_title}.m3u8'. Found: {found_count}, Missing: {missing_count}")
            
        except Exception as e:
            self.log(f"Critical Error: {e}")
            logging.exception("Playlist generation failed")

    def stop(self):
        self.stop_event.set()
