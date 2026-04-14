import html

import streamlit as st


CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@500;700;800&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
    --bg: #06070b;
    --panel: rgba(15, 19, 27, 0.94);
    --panel-soft: rgba(21, 26, 36, 0.92);
    --text: #f6fff8;
    --muted: #99a8b5;
    --line: rgba(90, 255, 168, 0.14);
    --accent: #1ed760;
    --accent-deep: #159447;
}

html, body, [class*="css"] {
    font-family: 'Manrope', sans-serif;
}

.stApp {
    color: var(--text);
    background:
        radial-gradient(circle at 8% 10%, rgba(30, 215, 96, 0.12), transparent 24%),
        radial-gradient(circle at 88% 12%, rgba(82, 107, 255, 0.10), transparent 22%),
        linear-gradient(180deg, #07090d 0%, #090c12 42%, #05060a 100%);
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(30, 215, 96, 0.06), transparent 24%),
        linear-gradient(180deg, rgba(9, 12, 18, 0.95), rgba(5, 6, 10, 0.98));
}

header[data-testid="stHeader"] {
    background: linear-gradient(180deg, rgba(7, 9, 13, 0.9), rgba(7, 9, 13, 0.3));
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

[data-testid="stSidebar"] {
    width: 33% !important;
    min-width: 33% !important;
    max-width: 33% !important;
    background:
        radial-gradient(circle at 18% 8%, rgba(30, 215, 96, 0.12), transparent 22%),
        linear-gradient(180deg, #161b26 0%, #0c1017 52%, #080b11 100%) !important;
    border-right: 1px solid var(--line);
}

[data-testid="stSidebar"] > div:first-child {
    width: 33% !important;
    min-width: 33% !important;
    max-width: 33% !important;
}

[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

.hero-shell {
    position: relative;
    overflow: hidden;
    padding: 2.2rem 2rem;
    border-radius: 28px;
    border: 1px solid var(--line);
    background:
        radial-gradient(circle at 82% 18%, rgba(95, 242, 180, 0.18), transparent 18%),
        radial-gradient(circle at 12% 14%, rgba(30, 215, 96, 0.14), transparent 24%),
        linear-gradient(135deg, rgba(17, 33, 27, 0.98), rgba(9, 15, 16, 0.98) 55%, rgba(7, 10, 14, 0.98));
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.34);
    margin-bottom: 1.4rem;
}

.hero-kicker {
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.24em;
    color: #90e5b2;
    font-weight: 800;
    margin-bottom: 0.8rem;
}

.hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 3rem;
    line-height: 0.95;
    letter-spacing: -0.04em;
    margin: 0;
    color: #f9fff9;
}

.hero-copy {
    max-width: 760px;
    margin-top: 1rem;
    color: #aebbc5;
    line-height: 1.72;
    font-size: 1rem;
}

.section-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.1rem;
    color: #edfdf2;
    margin: 0.3rem 0 1rem 0;
}

.track-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.95rem 1rem;
    margin-bottom: 0.85rem;
    border-radius: 18px;
    border: 1px solid rgba(90, 255, 168, 0.1);
    background: linear-gradient(135deg, rgba(20, 25, 35, 0.98), rgba(10, 13, 19, 0.98));
    box-shadow: 0 16px 38px rgba(0, 0, 0, 0.24);
}

.track-cover {
    width: 64px;
    height: 64px;
    border-radius: 14px;
    object-fit: cover;
    flex-shrink: 0;
    background: #11151c;
}

.track-meta {
    flex: 1;
    min-width: 0;
}

.track-title {
    font-size: 1rem;
    font-weight: 800;
    color: #f6fff8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.track-subtitle {
    margin-top: 0.22rem;
    font-size: 0.88rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.track-link {
    width: 42px;
    height: 42px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    border-radius: 999px;
    text-decoration: none;
    background: linear-gradient(135deg, var(--accent), var(--accent-deep));
    color: #041109 !important;
    font-weight: 900;
}

.meta-note {
    margin: 0.35rem 0 1rem 0;
    padding: 0.9rem 1rem;
    border-radius: 15px;
    border: 1px solid rgba(90, 255, 168, 0.14);
    background: rgba(17, 30, 24, 0.52);
    color: #d7fce4;
    font-size: 0.92rem;
    line-height: 1.6;
}

.stTextArea textarea,
.stButton button,
.stSlider {
    font-family: 'Manrope', sans-serif !important;
}

.stTextArea textarea,
.stTextArea > div > div {
    background: linear-gradient(180deg, rgba(24, 29, 38, 0.96), rgba(12, 16, 23, 0.98)) !important;
    color: var(--text) !important;
    border: 1px solid rgba(90, 255, 168, 0.12) !important;
}

.stTextArea textarea::placeholder {
    color: #7f8d98 !important;
}

.stButton > button {
    width: 100%;
    border: none;
    border-radius: 14px;
    background: linear-gradient(135deg, var(--accent), var(--accent-deep));
    color: #051109;
    font-weight: 800;
    padding: 0.84rem 1rem;
}
</style>
"""


def inject_custom_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_hero_section() -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-kicker">Spotify AI Portal</div>
            <h1 class="hero-title">Describe the vibe.<br/>Let the seeds find the sound.</h1>
            <div class="hero-copy">
                A dark audio studio interface powered by CLAP semantics and pure seed-based Spotify recommendations.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_track_card(track: dict) -> None:
    album = track.get("album") or {}
    images = album.get("images") or []
    image_url = "https://placehold.co/64x64/11151c/f4fff8?text=%E2%99%AA"

    if images and isinstance(images, list):
        first_image = images[0] or {}
        image_url = first_image.get("url") or image_url

    artists = track.get("artists") or []
    artist_names = ", ".join((artist or {}).get("name", "Unknown Artist") for artist in artists) or "Unknown Artist"
    track_name = track.get("name") or "Unknown Track"
    album_name = album.get("name") or "Unknown Album"
    spotify_url = (track.get("external_urls") or {}).get("spotify", "#")

    st.markdown(
        f"""
        <div class="track-card">
            <img class="track-cover" src="{image_url}" alt="album art" />
            <div class="track-meta">
                <div class="track-title">{html.escape(str(track_name))}</div>
                <div class="track-subtitle">{html.escape(f'{artist_names} • {album_name}')}</div>
            </div>
            <a class="track-link" href="{spotify_url}" target="_blank">↗</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
