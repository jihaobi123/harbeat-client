import streamlit as st

from services.library_service import ingest_tracks, list_collections
from services.rerank_service import rerank_tracks
from services.search_service import search_collection
from services.spotify_service import fetch_playlist_tracks, get_track_by_id, search_tracks
from services.vibe_service import interpret_vibe
from styles import inject_custom_css, render_hero_section, render_local_result_card, render_panel_header, render_track_card


st.set_page_config(
    page_title="FRe Music Lab",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_hero_section()


def hydrate_local_results_with_spotify(items: list[dict]) -> list[dict]:
    hydrated = []
    for item in items:
        spotify_id = str(item.get("spotify_id") or "").strip()
        spotify_track = get_track_by_id(spotify_id) if spotify_id else None
        if spotify_track:
            merged = dict(item)
            merged.update(spotify_track)
            merged["track_name"] = item.get("track_name") or spotify_track.get("name")
            merged["artist"] = item.get("artist")
            merged["distance"] = item.get("distance")
            merged["bpm"] = item.get("bpm")
            merged["energy"] = item.get("energy")
            merged["collection"] = item.get("collection")
            hydrated.append(merged)
        else:
            hydrated.append(item)
    return hydrated


def build_badges(item: dict) -> list[str]:
    badges = []
    if item.get("distance") is not None:
        badges.append(f"distance {item.get('distance')}")
    if item.get("bpm") is not None:
        badges.append(f"bpm {item.get('bpm')}")
    if item.get("energy") is not None:
        badges.append(f"energy {item.get('energy')}")
    if item.get("collection"):
        badges.append(f"collection {item.get('collection')}")
    return badges


left_col, middle_col, right_col = st.columns(3, gap="large")

with left_col:
    st.markdown('<div class="workflow-panel">', unsafe_allow_html=True)
    render_panel_header(
        "Workflow 01",
        "Vibe recommendation",
        "Describe a scene, mood, or movement. The app will recommend Spotify tracks, analyze the audio, and expand your local semantic library.",
        "Best for quickly growing the database from taste-based prompts.",
    )
    vibe_text = st.text_area(
        "Describe the vibe",
        placeholder="Music for melancholic midnight driving in a rainy city",
        height=160,
        key="vibe_input",
    )
    vibe_collection = st.text_input(
        "Store recommended songs into collection",
        value="local_music_library",
        key="vibe_collection",
    )
    vibe_limit = st.slider(
        "How many Spotify candidates to analyze",
        min_value=3,
        max_value=12,
        value=6,
        key="vibe_limit",
    )
    vibe_search_clicked = st.button("Recommend, analyze, and store", type="primary", key="vibe_button")

    if vibe_search_clicked:
        if not vibe_text.strip():
            st.warning("Please describe the vibe you want to hear.")
        else:
            with st.spinner("Searching Spotify, reranking, and ingesting into the local library..."):
                vibe_data = interpret_vibe(vibe_text)
                candidates = search_tracks(vibe_data["search_query"], limit=vibe_limit)
                ranked_tracks = rerank_tracks(vibe_data["vibe_description"], candidates)
                ingest_results = ingest_tracks(ranked_tracks, collection_name=vibe_collection.strip() or "local_music_library")

            st.markdown(
                f"""
                <div class="meta-note">
                    Search query: <strong>{vibe_data['search_query']}</strong><br/>
                    Rerank vibe: <strong>{vibe_data['vibe_description']}</strong><br/>
                    Candidates: <strong>{len(ranked_tracks)}</strong><br/>
                    Stored successfully: <strong>{sum(1 for item in ingest_results if item.get('success'))}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )

            for index, track in enumerate(ranked_tracks, start=1):
                render_track_card(track, rank=index, subtitle_note="Spotify recommendation")
    st.markdown('</div>', unsafe_allow_html=True)

with middle_col:
    st.markdown('<div class="workflow-panel">', unsafe_allow_html=True)
    render_panel_header(
        "Workflow 02",
        "Playlist ingest + semantic search",
        "Drop a Spotify playlist, vectorize its tracks with the Rec0 pipeline, and then search that new library slice or an existing collection using a custom description.",
        "Best for turning a playlist into a searchable semantic crate.",
    )
    playlist_url = st.text_input(
        "Spotify playlist link or URI",
        placeholder="https://open.spotify.com/playlist/...",
        key="playlist_url",
    )
    playlist_prompt = st.text_area(
        "Describe what you want from that playlist",
        placeholder="Energetic street dance tracks with crisp drums and confident motion",
        height=140,
        key="playlist_prompt",
    )
    existing_collections = list_collections()
    collection_options = existing_collections[:] if existing_collections else ["local_music_library"]
    playlist_target_mode = st.radio(
        "Search library source",
        options=["Use uploaded playlist collection", "Use existing local collection"],
        key="playlist_target_mode",
    )
    playlist_collection_name = st.text_input(
        "Uploaded playlist collection name",
        value="uploaded_playlist",
        key="playlist_collection_name",
    )
    selected_existing_collection = st.selectbox(
        "Existing local collection",
        options=collection_options,
        index=0,
        key="selected_existing_collection",
    )
    playlist_search_clicked = st.button("Ingest playlist and run semantic search", type="primary", key="playlist_button")

    if playlist_search_clicked:
        if not playlist_url.strip() or not playlist_prompt.strip():
            st.warning("Please provide both a playlist link and a description.")
        else:
            target_collection = playlist_collection_name.strip() or "uploaded_playlist"
            with st.spinner("Fetching playlist, analyzing audio, storing embeddings, then searching semantically..."):
                playlist_tracks = fetch_playlist_tracks(playlist_url)
                playlist_ingest_results = ingest_tracks(playlist_tracks, collection_name=target_collection)
                search_collection_name = target_collection if playlist_target_mode == "Use uploaded playlist collection" else selected_existing_collection
                playlist_results = search_collection(playlist_prompt, collection_name=search_collection_name, top_k=10)
                hydrated_playlist_results = hydrate_local_results_with_spotify(playlist_results)

            st.markdown(
                f"""
                <div class="meta-note">
                    Playlist tracks fetched: <strong>{len(playlist_tracks)}</strong><br/>
                    Stored successfully: <strong>{sum(1 for item in playlist_ingest_results if item.get('success'))}</strong><br/>
                    Search collection: <strong>{search_collection_name}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )

            for index, item in enumerate(hydrated_playlist_results, start=1):
                render_track_card(
                    item,
                    rank=index,
                    badges=build_badges(item),
                    subtitle_note="Semantic match from playlist workflow",
                )
    st.markdown('</div>', unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="workflow-panel">', unsafe_allow_html=True)
    render_panel_header(
        "Workflow 03",
        "Search local library",
        "Use a free-text description to search the local semantic database and get ranked Spotify-ready results with artwork and direct links.",
        "Best for browsing the full evolving archive like a mood-driven record shelf.",
    )
    local_prompt = st.text_area(
        "Describe the sound you want from the local database",
        placeholder="Warm old-school hip-hop with dusty drums and late-night city mood",
        height=160,
        key="local_prompt",
    )
    all_collections = list_collections()
    local_collection = st.selectbox(
        "Choose local collection",
        options=all_collections if all_collections else ["local_music_library"],
        index=0,
        key="local_collection",
    )
    local_search_clicked = st.button("Search local semantic database", type="primary", key="local_button")

    if local_search_clicked:
        if not local_prompt.strip():
            st.warning("Please enter a description for semantic search.")
        else:
            with st.spinner("Searching the local semantic database..."):
                local_results = search_collection(local_prompt, collection_name=local_collection, top_k=12)
                hydrated_results = hydrate_local_results_with_spotify(local_results)

            st.markdown(
                f"""
                <div class="meta-note">
                    Search collection: <strong>{local_collection}</strong><br/>
                    Results: <strong>{len(hydrated_results)}</strong><br/>
                    View: <strong>Spotify links with album artwork when available</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )

            for index, item in enumerate(hydrated_results, start=1):
                render_track_card(
                    item,
                    rank=index,
                    badges=build_badges(item),
                    subtitle_note="Local semantic match",
                )
    st.markdown('</div>', unsafe_allow_html=True)
