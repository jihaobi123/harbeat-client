import os
import warnings
from pathlib import Path

os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
warnings.filterwarnings(
    "ignore",
    message=r"Accessing `__path__` from .*",
)

import streamlit as st

from services.dj_planner_service import DJContextPlanner, SessionContext
from services.library_service import ingest_tracks, list_collections
from services.rerank_service import rerank_tracks
from services.search_service import fetch_with_multiplier, search_collection
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


def parse_style_ratios(raw: str) -> dict[str, float]:
    ratios: dict[str, float] = {}
    for token in str(raw or "").split(","):
        chunk = token.strip()
        if not chunk or ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        name = name.strip().lower()
        if not name:
            continue
        try:
            ratios[name] = float(value.strip())
        except ValueError:
            continue
    return ratios


def parse_energy_curve(raw: str) -> list[float]:
    values: list[float] = []
    for token in str(raw or "").split(","):
        item = token.strip()
        if not item:
            continue
        try:
            value = float(item)
        except ValueError:
            continue
        values.append(max(1.0, min(10.0, value)))
    return values


if "dj_plan" not in st.session_state:
    st.session_state["dj_plan"] = None
if "dj_playlist_tracks" not in st.session_state:
    st.session_state["dj_playlist_tracks"] = []
if "dj_bpm_by_track" not in st.session_state:
    st.session_state["dj_bpm_by_track"] = {}
if "dj_track_info" not in st.session_state:
    st.session_state["dj_track_info"] = {}


left_col, middle_col, right_col, dj_col = st.columns(4, gap="large")

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
    vibe_recall_limit = st.slider(
        "How many Spotify candidates to recall",
        min_value=10,
        max_value=50,
        value=30,
        step=5,
        key="vibe_recall_limit",
    )
    vibe_final_limit = st.slider(
        "How many top-ranked tracks to show and ingest",
        min_value=3,
        max_value=15,
        value=10,
        key="vibe_final_limit",
    )
    vibe_search_clicked = st.button("Recommend, analyze, and store", type="primary", key="vibe_button")

    if vibe_search_clicked:
        if not vibe_text.strip():
            st.warning("Please describe the vibe you want to hear.")
        else:
            with st.spinner("Recalling from Spotify, reranking semantically, and ingesting top tracks..."):
                vibe_data = interpret_vibe(vibe_text)
                candidates = search_tracks(vibe_data["search_query"], limit=vibe_recall_limit)
                ranked_candidates = rerank_tracks(vibe_data["vibe_description"], candidates)
                final_tracks = ranked_candidates[:vibe_final_limit]
                ingest_results = ingest_tracks(final_tracks, collection_name=vibe_collection.strip() or "local_music_library")

            st.markdown(
                f"""
                <div class="meta-note">
                    Search query: <strong>{vibe_data['search_query']}</strong><br/>
                    Rerank vibe: <strong>{vibe_data['vibe_description']}</strong><br/>
                    Recalled from Spotify: <strong>{len(candidates)}</strong><br/>
                    Reranked: <strong>{len(ranked_candidates)}</strong><br/>
                    Final shown & ingested: <strong>{len(final_tracks)}</strong><br/>
                    Stored successfully: <strong>{sum(1 for item in ingest_results if item.get('success'))}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )

            for index, track in enumerate(final_tracks, start=1):
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

with dj_col:
    st.markdown('<div class="workflow-panel">', unsafe_allow_html=True)
    render_panel_header(
        "Workflow 04",
        "Auto DJ plan + mixdown",
        "Input a playlist link, auto-analyze tracks, generate DJ ordering with scores, then confirm to render a quick mix preview.",
        "Best for semi-automatic set building from a playlist.",
    )

    dj_source_mode = st.radio(
        "Planning music pool",
        options=["Use playlist link", "Use existing local collection"],
        key="dj_source_mode",
    )
    available_collections = list_collections()
    selected_pool_collection = st.selectbox(
        "Existing local collection (for local mode)",
        options=available_collections if available_collections else ["local_music_library"],
        index=0,
        key="dj_pool_collection",
    )

    if dj_source_mode == "Use playlist link":
        dj_playlist_url = st.text_input(
            "Spotify playlist link or URI",
            placeholder="https://open.spotify.com/playlist/...",
            key="dj_playlist_url",
        )
        dj_collection = st.text_input(
            "Collection for analysis storage",
            value="dj_workbench",
            key="dj_collection",
        )
    else:
        dj_playlist_url = ""
        dj_collection = selected_pool_collection
        st.caption("Playlist inputs are hidden in local-collection mode.")
    dj_scene = st.selectbox(
        "Scene type",
        options=["battle", "cypher", "party", "exercise"],
        index=0,
        key="dj_scene",
    )
    dj_style_ratios_raw = st.text_input(
        "Style ratios (optional)",
        value="hiphop:0.6,popping:0.4",
        key="dj_style_ratios",
    )
    dj_target_length = st.slider(
        "Target set length",
        min_value=2,
        max_value=12,
        value=6,
        step=1,
        key="dj_target_length",
    )
    dj_energy_curve_raw = st.text_input(
        "Target energy curve (comma-separated, 1-10)",
        value="7.0,7.8,8.4,7.6,8.6,7.9",
        key="dj_energy_curve",
        help="长度不足会自动补齐，超出会截断。",
    )
    dj_mix_duration_minutes = st.slider(
        "Target mix total duration (minutes)",
        min_value=3,
        max_value=60,
        value=10,
        step=1,
        key="dj_mix_duration_minutes",
    )

    analyze_clicked = st.button("Analyze playlist and generate DJ plan", type="primary", key="dj_plan_button")

    if analyze_clicked:
        if dj_source_mode == "Use playlist link" and not dj_playlist_url.strip():
            st.warning("Please provide a playlist link.")
        else:
            try:
                style_ratios = parse_style_ratios(dj_style_ratios_raw)
                target_energy_curve = parse_energy_curve(dj_energy_curve_raw)
                context = SessionContext(scene_type=dj_scene, style_ratios=style_ratios)
                planner = DJContextPlanner()

                playlist_tracks: list[dict] = []
                successful_count = 0
                planning_collection = selected_pool_collection

                if dj_source_mode == "Use playlist link":
                    planning_collection = dj_collection.strip() or "dj_workbench"
                    with st.spinner("Fetching playlist, downloading audio for analysis, and building DJ sequence..."):
                        playlist_tracks = fetch_playlist_tracks(dj_playlist_url)
                        ingest_results = ingest_tracks(playlist_tracks, collection_name=planning_collection)

                    successful = [item for item in ingest_results if item.get("success")]
                    successful_count = len(successful)
                else:
                    with st.spinner("Building DJ sequence from existing local collection..."):
                        successful = []
                    successful_count = 0

                oversampled_candidates = fetch_with_multiplier(
                    collection_name=planning_collection,
                    target_length=dj_target_length,
                    style_ratios=style_ratios,
                    multiplier=5,
                    query_text=None,
                )

                bpm_by_track: dict[str, float] = {}
                track_info: dict[str, dict] = {}
                for row in oversampled_candidates:
                    track_id = str(row.get("spotify_id") or row.get("track_id") or row.get("id") or "").strip()
                    if not track_id:
                        continue
                    bpm_by_track[track_id] = float(row.get("bpm") or row.get("BPM") or 0.0)
                    track_info[track_id] = {
                        "track_name": row.get("track_name") or "Unknown",
                        "artist": row.get("artist") or "Unknown",
                        "bpm": row.get("bpm") or row.get("BPM"),
                        "energy": row.get("energy"),
                        "key": row.get("key") or "",
                    }

                plan = planner.generate_plan(
                    candidates=oversampled_candidates,
                    context=context,
                    target_length=dj_target_length,
                    target_energy_curve=target_energy_curve,
                    explain=True,
                )

                st.session_state["dj_plan"] = plan
                st.session_state["dj_playlist_tracks"] = playlist_tracks
                st.session_state["dj_bpm_by_track"] = bpm_by_track
                st.session_state["dj_track_info"] = track_info
                st.session_state["dj_plan_source_mode"] = dj_source_mode

                source_label = "playlist" if dj_source_mode == "Use playlist link" else "local collection"
                st.success("DJ planning completed. Review order and click confirm to start mix rendering.")
                st.markdown(
                    f"""
                    <div class="meta-note">
                        Planning source: <strong>{source_label}</strong><br/>
                        Playlist tracks fetched: <strong>{len(playlist_tracks)}</strong><br/>
                        Analyzed & stored: <strong>{successful_count}</strong><br/>
                        Oversampled pool: <strong>{len(oversampled_candidates)}</strong><br/>
                        Planned order length: <strong>{len(plan.get('ordered_tracks', []))}</strong>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            except Exception as exc:
                st.error(f"DJ planning failed: {exc}")

    current_plan = st.session_state.get("dj_plan") or {}
    if current_plan.get("ordered_tracks"):
        ordered_rows = []
        for idx, track_id in enumerate(current_plan.get("ordered_tracks", []), start=1):
            info = (st.session_state.get("dj_track_info") or {}).get(track_id, {})
            ordered_rows.append(
                {
                    "rank": idx,
                    "track_id": track_id,
                    "track_name": info.get("track_name", "Unknown"),
                    "artist": info.get("artist", "Unknown"),
                    "bpm": info.get("bpm"),
                    "energy": info.get("energy"),
                    "key": info.get("key", ""),
                }
            )

        st.markdown("**Planned order**")
        st.dataframe(ordered_rows, use_container_width=True, hide_index=True)

        transition_rows = []
        for t in current_plan.get("transitions", []):
            explain = t.get("explain") or {}
            transition_rows.append(
                {
                    "from": t.get("from_track"),
                    "to": t.get("to_track"),
                    "score": t.get("score"),
                    "strategy": t.get("strategy"),
                    "fallback_reason": t.get("fallback_reason"),
                    "sync_target_bpm": t.get("sync_target_bpm"),
                    "target_energy": explain.get("target_energy"),
                    "selected_energy": explain.get("selected_energy"),
                    "energy_match": explain.get("energy_match"),
                    "transition_score": explain.get("transition_score"),
                }
            )

        st.markdown("**Transition scores**")
        st.dataframe(transition_rows, use_container_width=True, hide_index=True)

        st.info("Mix rendering is disabled in this branch. Planning outputs are available above.")

    st.markdown('</div>', unsafe_allow_html=True)
