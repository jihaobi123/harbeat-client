import warnings
warnings.filterwarnings("ignore")
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import streamlit as st

from ai_engine import interpret_vibe, rerank
from spotify_client import get_smart_candidates
from styles import inject_custom_css, render_hero_section, render_track_card


st.set_page_config(
    page_title="Spotify AI Portal",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

with st.sidebar:
    st.markdown("## Tune the search")
    vibe_text = st.text_area(
        "Describe the vibe",
        placeholder="Music for melancholic midnight driving in a rainy city",
        height=220,
    )
    search_clicked = st.button("Search", type="primary")

render_hero_section()
st.markdown('<div class="section-title">Recommended Tracks</div>', unsafe_allow_html=True)

if search_clicked:
    if not vibe_text.strip():
        st.warning("Please describe the vibe you want to hear.")
    else:
        with st.spinner("Translating vibe, searching, and reranking..."):
            vibe_data = interpret_vibe(vibe_text)
            raw_tracks, search_debug = get_smart_candidates(vibe_data["search_query"])
            final_tracks = rerank(vibe_data["vibe_description"], raw_tracks)[:10]

        st.markdown(
            f"""
            <div class="meta-note">
                Search query: <strong>{vibe_data['search_query']}</strong><br/>
                Rerank vibe: <strong>{vibe_data['vibe_description']}</strong><br/>
                Candidate count: <strong>{len(raw_tracks)}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if final_tracks:
            for track in final_tracks:
                render_track_card(track)
        else:
            st.warning("Spotify didn't return any songs for this vibe. Try adjusting the description!")
            st.caption("Search diagnostics")
            for row in search_debug[:12]:
                st.text(row)
else:
    st.info("Describe a scene, mood, or motion in the sidebar, then press Search.")
