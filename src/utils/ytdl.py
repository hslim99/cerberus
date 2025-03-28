def get_ytdl_options(cookiefile: str | None = None):
    options = {
        "format": "bestaudio/best",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "source_address": "0.0.0.0",
    }
    if cookiefile:
        options["cookiefile"] = cookiefile
    return options


ffmpeg_options = {
    "before_options": "-fflags +genpts -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -re",
    "options": "-vn -bufsize 256k -ar 48000 -ac 2",
}
