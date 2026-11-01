"""Wear & Wonder Automation: Stages 1–5 Content Production Workspace."""
import json
from pathlib import Path
import streamlit as st

from app.approval_workflow import (
    ApprovalStatus,
    WorkflowStage,
    approve_research,
    can_proceed_to_stage,
    get_workflow_prerequisites,
)
from app.fashion_ai import interpret_idea_with_gemini
from app.idea_intake import create_research_brief, interpret_idea, save_research_brief
from app.image_generation import (
    approve_all_images_in_chatgpt,
    approve_image,
    approve_image_in_chatgpt,
    import_generated_image,
    import_image_from_path,
    prepare_image_prompts,
    reject_image,
)
from app.model_library import (
    ALLOWED_MODELS,
    load_models,
    save_model,
    set_model_approval,
)
from app.research import execute_fashion_research
from app.storage import (
    get_brief_by_id,
    get_research_data,
    load_all_briefs,
    load_audit_events,
    load_image_assets,
    load_outfits,
    load_video_assets,
)
from app.styling import (
    approve_all_outfits,
    approve_single_outfit,
    edit_outfit,
    generate_outfit_proposals,
    reject_single_outfit,
)
from app.topic_router import (
    classify_topic,
    get_topic_config,
    list_supported_topics,
)

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="Wear & Wonder",
    page_icon="👗",
    layout="wide",
)

PROJECT_DIR = Path(__file__).resolve().parent

st.title("Wear & Wonder")
st.caption("AI-assisted fashion content production workspace · Stages 1–5")

# --------------------------------------------------
# SIDEBAR: ACTIVE BRIEF SELECTOR & GATE STATUS
# --------------------------------------------------
all_briefs = load_all_briefs()
brief_options = {
    f"{b.get('brief_id', 'unknown')[:8]} — {b.get('idea_original', 'Untitled')[:40]}...": b.get("brief_id")
    for b in all_briefs if isinstance(b, dict) and b.get("brief_id")
}

with st.sidebar:
    st.header("Project Navigator")
    if brief_options:
        # Determine default index
        active_id = st.session_state.get("active_brief_id")
        index = 0
        brief_keys = list(brief_options.keys())
        if active_id:
            for i, k in enumerate(brief_keys):
                if brief_options[k] == active_id:
                    index = i
                    break

        selected_label = st.selectbox(
            "Active Project Brief",
            options=brief_keys,
            index=index,
            key="sidebar_brief_select",
        )
        active_brief_id = brief_options[selected_label]
        st.session_state["active_brief_id"] = active_brief_id
    else:
        st.info("No saved briefs found. Start in the Idea Studio tab.")
        active_brief_id = None

    if st.button("➕ Start New Brief", use_container_width=True):
        st.session_state.pop("pending_brief", None)
        st.session_state.pop("active_brief_id", None)
        st.rerun()

    st.divider()

    # Display Stage Gates for Active Brief
    if active_brief_id:
        st.subheader("Workflow Gates")
        prereqs = get_workflow_prerequisites(active_brief_id)

        st.markdown(f"**Brief:** `{active_brief_id[:8]}`")

        def status_pill(label: str, is_done: bool, text: str):
            color = "green" if is_done else "orange"
            st.markdown(f"- **{label}:** :{color}[{text}]")

        status_pill("1. Idea Brief", True, "SAVED")
        status_pill(
            "2. Research",
            prereqs["research_approved"],
            "APPROVED" if prereqs["research_approved"] else ("COMPLETED" if prereqs["research_completed"] else "PENDING"),
        )
        status_pill(
            "3. Outfits",
            prereqs["outfits_approved"],
            "APPROVED" if prereqs["outfits_approved"] else ("PROPOSED" if prereqs["has_outfits"] else "PENDING"),
        )
        status_pill(
            "4. Images",
            prereqs["images_approved"],
            "APPROVED" if prereqs["images_approved"] else ("GENERATED" if prereqs["images_generated"] else "PENDING"),
        )
        status_pill(
            "5. Video Clips",
            prereqs["videos_approved"],
            "APPROVED" if prereqs["videos_approved"] else ("GENERATED" if prereqs["videos_generated"] else "PENDING"),
        )

        st.divider()
        if prereqs["stage_6_ready"]:
            st.success("🎉 All assets approved! Ready for Stage 6: Video Editing.")
        else:
            st.info("🔒 Stage 6 Editing locked until all clips are approved.")


# --------------------------------------------------
# MAIN WORKSPACE TABS
# --------------------------------------------------
tab_idea, tab_research, tab_outfits, tab_images, tab_videos, tab_models, tab_status = st.tabs([
    "💡 Idea Studio",
    "🔎 Research",
    "👗 Outfit Proposals",
    "📸 Image Studio",
    "🎬 Video Studio",
    "👤 Master Models",
    "📊 Workflow Status",
])


# --------------------------------------------------
# TAB 1: IDEA STUDIO (Stage 1)
# --------------------------------------------------
with tab_idea:
    st.subheader("Stage 1: Idea Studio")
    st.write("Convert your free-text fashion video idea into a structured, editable research brief.")

    with st.form("idea_form"):
        idea_input = st.text_area(
            "What fashion video do you want to create?",
            placeholder="Example: Create six jeans and top combinations for college girls using my female master model.",
            height=110,
        )

        ref_col, topic_col = st.columns(2)
        with ref_col:
            reference_url = st.text_input("Reference URL (optional)")
        with topic_col:
            topic_options = [t.topic_id for t in list_supported_topics()]
            selected_topic = st.selectbox(
                "Primary fashion topic",
                topic_options,
                format_func=lambda x: get_topic_config(x).display_name,
            )

        additional_requirements = st.text_area("Additional requirements (optional)", height=70)

        ai_col, local_col = st.columns(2)
        with ai_col:
            submit_ai = st.form_submit_button("✨ Review with Gemini AI", type="primary", use_container_width=True)
        with local_col:
            submit_local = st.form_submit_button("⚡ Quick Local Review", use_container_width=True)

    if submit_ai or submit_local:
        if not idea_input.strip():
            st.error("Please enter a fashion video idea.")
        else:
            clean_req = additional_requirements.strip() or None
            clean_ref = reference_url.strip() or None

            if submit_ai:
                try:
                    with st.spinner("Gemini is interpreting your idea..."):
                        ai_result = interpret_idea_with_gemini(
                            idea=idea_input,
                            additional_requirements=clean_req,
                            reference_url=clean_ref,
                        )
                    brief = create_research_brief(
                        idea=idea_input,
                        requested_characters=ai_result["requested_characters"],
                        audience=ai_result["audience"],
                        outfit_count=ai_result["outfit_count"],
                        additional_requirements=clean_req,
                        primary_topic=ai_result.get("primary_topic") or selected_topic,
                    )
                    brief["reference_url"] = clean_ref
                    brief["ai_analysis"] = ai_result
                    brief["interpretation_method"] = "GEMINI_API"
                    st.session_state["pending_brief"] = brief
                    st.success("AI interpretation prepared! Review the draft below.")
                except Exception as exc:
                    st.error(f"Could not prepare AI brief: {exc}. You can use the Quick Local Review option.")
            else:
                try:
                    brief = create_research_brief(
                        idea=idea_input,
                        additional_requirements=clean_req,
                        primary_topic=selected_topic,
                    )
                    brief["reference_url"] = clean_ref
                    brief["interpretation_method"] = "LOCAL_RULES"
                    st.session_state["pending_brief"] = brief
                    st.success("Local brief prepared! Review the draft below.")
                except Exception as exc:
                    st.error(f"Could not prepare brief: {exc}")

    # Review & Edit Pending Draft
    if "pending_brief" in st.session_state:
        draft = st.session_state["pending_brief"]
        st.divider()
        st.subheader("Review Draft Research Brief")
        st.info("Review and adjust the extracted details before confirming. Research and outfit approvals remain PENDING.")

        ai_an = draft.get("ai_analysis", {})
        if ai_an:
            with st.expander("Gemini Styling Analysis & Plan", expanded=True):
                if ai_an.get("concept_summary"):
                    st.markdown(f"**Concept Summary:** {ai_an['concept_summary']}")
                if ai_an.get("styling_direction"):
                    st.markdown(f"**Styling Direction:** {ai_an['styling_direction']}")
                if ai_an.get("research_plan"):
                    st.markdown("**Research Tasks:**")
                    for t in ai_an["research_plan"]:
                        st.markdown(f"- {t}")

        st.markdown(f"**Original Idea:** {draft['idea_original']}")

        col_aud, col_count, col_top = st.columns(3)
        with col_aud:
            audience_opts = ["Not specified", "College girls", "College boys", "Couples", "General audience"]
            curr_aud = draft.get("audience") or "Not specified"
            draft_aud = st.selectbox(
                "Audience",
                audience_opts,
                index=audience_opts.index(curr_aud) if curr_aud in audience_opts else 0,
            )
        with col_count:
            curr_cnt = draft.get("outfit_count") or 6
            draft_cnt = st.number_input("Outfit Count", min_value=1, max_value=20, value=int(curr_cnt), step=1)
        with col_top:
            curr_top = draft.get("primary_topic", "general_fashion")
            draft_top = st.selectbox(
                "Primary Topic",
                topic_options,
                index=topic_options.index(curr_top) if curr_top in topic_options else 0,
                format_func=lambda x: get_topic_config(x).display_name,
            )

        model_labels = {"WW-CHAR-01": "Female Model 01", "WW-CHAR-02": "Female Model 02", "WW-CHAR-03": "Male Model 01"}
        draft_chars = st.multiselect(
            "Requested Master Characters",
            options=list(model_labels.keys()),
            default=draft.get("requested_characters", ["WW-CHAR-01"]),
            format_func=lambda x: f"{x} — {model_labels[x]}",
        )

        col_save, col_discard = st.columns(2)
        with col_save:
            if st.button("💾 Confirm Details and Save Brief", type="primary", use_container_width=True):
                try:
                    updated = create_research_brief(
                        idea=draft["idea_original"],
                        requested_characters=draft_chars,
                        audience=None if draft_aud == "Not specified" else draft_aud,
                        outfit_count=int(draft_cnt),
                        additional_requirements=draft.get("additional_requirements"),
                        primary_topic=draft_top,
                    )
                    updated["brief_id"] = draft["brief_id"]
                    updated["reference_url"] = draft.get("reference_url")
                    updated["ai_analysis"] = draft.get("ai_analysis", {})
                    updated["interpretation_method"] = draft.get("interpretation_method", "LOCAL_RULES")

                    save_research_brief(updated)
                    st.session_state["active_brief_id"] = updated["brief_id"]
                    st.session_state.pop("pending_brief", None)
                    st.session_state["saved_message"] = f"Brief {updated['brief_id'][:8]} saved successfully!"
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save brief: {exc}")

        with col_discard:
            if st.button("Discard Draft", use_container_width=True):
                st.session_state.pop("pending_brief", None)
                st.rerun()

    if "saved_message" in st.session_state:
        st.success(st.session_state.pop("saved_message"))


# --------------------------------------------------
# TAB 2: RESEARCH (Stage 2)
# --------------------------------------------------
with tab_research:
    st.subheader("Stage 2: Live Fashion Research with Source URLs")
    st.write("Retrieve real external fashion sources, verify URL reachability, and categorize factual evidence.")

    if not active_brief_id:
        st.warning("Please create or select an active project brief in the sidebar first.")
    else:
        current_brief = get_brief_by_id(active_brief_id)
        if not current_brief:
            st.error("Active brief record not found.")
        else:
            st.markdown(f"**Active Brief:** `{current_brief['brief_id'][:8]}` — *{current_brief['idea_original']}*")
            topic_cfg = get_topic_config(current_brief.get("primary_topic", "general_fashion"))
            st.caption(f"Topic: **{topic_cfg.display_name}** · Target Audience: **{current_brief.get('audience', 'General')}**")

            res_data = get_research_data(active_brief_id)
            existing_sources = res_data.get("sources", [])
            existing_summary = res_data.get("summary", {})

            col_run, col_appr = st.columns(2)
            with col_run:
                if st.button("🔎 Execute Live Fashion Research", type="primary", use_container_width=True):
                    with st.spinner("Formulating queries and querying live fashion references..."):
                        try:
                            result = execute_fashion_research(active_brief_id, verify_urls=True)
                            st.success(f"Retrieved {len(result['sources'])} sources ({result['summary']['verified_sources_count']} verified reachable).")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Research execution failed: {exc}")

            with col_appr:
                is_approved = current_brief.get("research_status") == ApprovalStatus.APPROVED.value
                if is_approved:
                    st.button("Research Approved", disabled=True, use_container_width=True)
                elif existing_sources:
                    if st.button("Approve Research Findings", type="primary", use_container_width=True):
                        approve_research(active_brief_id)
                        st.success("Research findings approved! Stage 3 Outfit Proposals unlocked.")
                        st.rerun()
                else:
                    st.button("Approve Research (Run Research First)", disabled=True, use_container_width=True)

            st.divider()

            if existing_sources:
                st.markdown("### Research Findings & Synthesis")
                if existing_summary:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Sources", existing_summary.get("total_sources_found", len(existing_sources)))
                    m2.metric("Verified Reachable URLs", existing_summary.get("verified_sources_count", 0))
                    m3.metric("Approval Status", current_brief.get("research_status", "PENDING"))

                    # Categorized Evidence
                    st.markdown("#### Factual Evidence vs AI Suggestions")
                    cat_col1, cat_col2 = st.columns(2)
                    with cat_col1:
                        st.markdown("**Verified Factual Evidence (From Sources)**")
                        for fact in existing_summary.get("verified_facts", []):
                            st.markdown(f"- {fact}")
                        if not existing_summary.get("verified_facts"):
                            st.caption("No verified facts recorded yet.")

                        st.markdown("**Reported Observations**")
                        for claim in existing_summary.get("reported_claims", []):
                            st.markdown(f"- {claim}")

                    with cat_col2:
                        st.markdown("**AI Styling Suggestions**")
                        for sug in existing_summary.get("ai_styling_suggestions", []):
                            st.markdown(f"- {sug}")

                        if existing_summary.get("evidence_gaps"):
                            st.warning("**Evidence Gaps Identified:**\n" + "\n".join(f"- {g}" for g in existing_summary["evidence_gaps"]))

                st.markdown("### Retrieved External Sources")
                for s in existing_sources:
                    with st.container(border=True):
                        s_title = s.get("title", "Fashion Reference")
                        s_url = s.get("url", "#")
                        v_status = s.get("verification_status", "UNVERIFIED")
                        status_color = "green" if v_status == "VERIFIED" else "red"

                        col_head, col_badge = st.columns([4, 1])
                        with col_head:
                            st.markdown(f"**[{s_title}]({s_url})**")
                            st.caption(f"Publisher: {s.get('publisher', 'Web Source')} · Type: {s.get('source_type', 'ARTICLE')}")
                        with col_badge:
                            st.markdown(f":{status_color}[**{v_status}**]")

                        st.write(f"*{s.get('relevant_excerpt', '')}*")
                        if s.get("supporting_evidence"):
                            st.caption(f"Supporting Evidence: {s['supporting_evidence']}")
            else:
                st.info("No research sources recorded for this brief yet. Click 'Execute Live Fashion Research' to begin.")


# --------------------------------------------------
# TAB 3: OUTFIT PROPOSALS (Stage 3)
# --------------------------------------------------
with tab_outfits:
    st.subheader("Stage 3: Outfit Proposals & 16-Dimension Validation")
    st.write("Generate, validate, edit, and approve complete fashion looks before image generation.")

    if not active_brief_id:
        st.warning("Please select an active project brief in the sidebar first.")
    else:
        can_proceed, reason = can_proceed_to_stage(active_brief_id, WorkflowStage.STAGE_3_OUTFITS)
        if not can_proceed:
            st.warning(f"🔒 {reason}")
        else:
            current_brief = get_brief_by_id(active_brief_id)
            outfits = load_outfits(active_brief_id)

            col_gen, col_app_all = st.columns(2)
            with col_gen:
                if st.button("✨ Generate Outfit Proposals", type="primary", use_container_width=True):
                    with st.spinner("Synthesizing validated outfit proposals..."):
                        proposals = generate_outfit_proposals(active_brief_id)
                        st.success(f"Generated {len(proposals)} candidate outfit proposals!")
                        st.rerun()

            with col_app_all:
                if outfits:
                    all_appr = all(o.get("approval_status") == ApprovalStatus.APPROVED.value for o in outfits)
                    if all_appr:
                        st.button("All Outfits Approved", disabled=True, use_container_width=True)
                    elif st.button("Approve All Outfits", type="primary", use_container_width=True):
                        approve_all_outfits(active_brief_id)
                        st.success("All outfit proposals approved! Stage 4 Image Studio unlocked.")
                        st.rerun()

            st.divider()

            if outfits:
                st.markdown(f"### Proposed Outfits ({len(outfits)} looks)")
                for o in outfits:
                    oid = o.get("outfit_id")
                    status = o.get("approval_status", "PENDING")
                    status_color = "green" if status == "APPROVED" else ("red" if status == "REJECTED" else "orange")

                    with st.container(border=True):
                        col_t, col_stat = st.columns([4, 1])
                        with col_t:
                            st.markdown(f"#### {o.get('outfit_title', oid)}")
                            st.caption(f"Outfit ID: `{oid}` · Assigned Model: **{o.get('assigned_character_id', 'WW-CHAR-01')}**")
                        with col_stat:
                            st.markdown(f":{status_color}[**{status}**]")
                            conf = o.get("confidence_score", 0.0)
                            st.caption(f"Score: **{int(conf * 100)}%**")

                        st.write(f"**Description:** {o.get('garment_descriptions', '')}")

                        # Garments breakdown
                        garments = o.get("garments", [])
                        if garments:
                            cols = st.columns(min(len(garments), 4))
                            for idx, g in enumerate(garments):
                                with cols[idx % len(cols)]:
                                    st.markdown(f"**{g.get('type', 'Piece')}:** {g.get('item', '')}")
                                    st.caption(f"Color: {g.get('color', '')} · Fabric: {g.get('fabric', '')}")

                        st.write(f"👟 **Footwear:** {o.get('footwear', 'Not specified')} · 👜 **Accessories:** {o.get('accessories', 'None')}")
                        st.caption(f"💡 **Styling Rationale:** {o.get('styling_rationale', '')}")

                        if o.get("warnings"):
                            st.warning("Styling Warnings:\n" + "\n".join(f"- {w}" for w in o["warnings"]))

                        # 16-Dimension Checklist Expander
                        with st.expander("16-Dimension Validation Checklist", expanded=False):
                            checks = o.get("validation_results", {})
                            c_cols = st.columns(2)
                            for i, (dim, res) in enumerate(checks.items()):
                                chk_color = "green" if res.get("status") == "PASS" else "orange"
                                with c_cols[i % 2]:
                                    st.markdown(f"- **{dim.replace('_', ' ').title()}:** :{chk_color}[{res.get('status')}] — *{res.get('notes', '')}*")

                        # Per-outfit actions
                        b1, b2, b3 = st.columns([1, 1, 2])
                        with b1:
                            if status == "APPROVED":
                                st.button("Approved", key=f"appr_dis_{oid}", disabled=True, use_container_width=True)
                            elif st.button("Approve", key=f"appr_{oid}", type="primary", use_container_width=True):
                                approve_single_outfit(active_brief_id, oid)
                                st.rerun()
                        with b2:
                            if st.button("Reject", key=f"rej_{oid}", use_container_width=True):
                                reject_single_outfit(active_brief_id, oid, reason="User rejected proposal.")
                                st.rerun()
                        with b3:
                            with st.popover(f"✏️ Edit {oid}"):
                                st.caption("Editing an outfit automatically invalidates downstream image and video assets!")
                                new_title = st.text_input("Title", value=o.get("outfit_title", ""), key=f"edit_t_{oid}")
                                new_desc = st.text_area("Garment Description", value=o.get("garment_descriptions", ""), key=f"edit_d_{oid}")
                                new_shoes = st.text_input("Footwear", value=o.get("footwear", ""), key=f"edit_sh_{oid}")
                                new_acc = st.text_input("Accessories", value=o.get("accessories", ""), key=f"edit_acc_{oid}")
                                if st.button("Save Changes & Re-validate", key=f"save_edit_{oid}", type="primary"):
                                    edit_outfit(
                                        brief_id=active_brief_id,
                                        outfit_id=oid,
                                        title=new_title,
                                        descriptions=new_desc,
                                        footwear=new_shoes,
                                        accessories=new_acc,
                                    )
                                    st.success(f"{oid} updated! Downstream assets invalidated.")
                                    st.rerun()
            else:
                st.info("No outfits generated yet. Click 'Generate Outfit Proposals' above.")


# --------------------------------------------------
# TAB 4: IMAGE STUDIO (Stage 4: ChatGPT-Direct Mode)
# --------------------------------------------------
with tab_images:
    st.subheader("Stage 4: Image Prompts & ChatGPT-Direct Studio")
    st.write(
        "Generate and review each look directly in ChatGPT using your approved master model reference. "
        "When satisfied with a look in ChatGPT, click **Approved in ChatGPT → Next Look** to advance seamlessly to Stage 5."
    )

    if not active_brief_id:
        st.warning("Please select an active project brief in the sidebar first.")
    else:
        can_proceed, reason = can_proceed_to_stage(active_brief_id, WorkflowStage.STAGE_4_IMAGES)
        if not can_proceed:
            st.warning(f"🔒 {reason}")
        else:
            image_assets = load_image_assets(active_brief_id)

            if not image_assets:
                st.info("Outfits are approved! Generate the optimized ChatGPT generation prompts below.")
                if st.button("🎨 Prepare Image Prompts for Approved Outfits", type="primary"):
                    try:
                        assets = prepare_image_prompts(active_brief_id)
                        st.success(f"Prepared {len(assets)} image prompts!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not prepare image prompts: {exc}")
            else:
                total_looks = len(image_assets)
                approved_count = sum(1 for img in image_assets if img.get("approval_status") == "APPROVED")

                # Top Progress and Quick-Action Bar
                top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
                with top_col1:
                    st.progress(approved_count / total_looks, text=f"Stage 4 Progress: {approved_count} of {total_looks} looks approved in ChatGPT")
                with top_col2:
                    st.link_button("🚀 Open ChatGPT", "https://chatgpt.com", use_container_width=True)
                with top_col3:
                    if approved_count < total_looks:
                        if st.button("⚡ Approve All in ChatGPT", use_container_width=True, help="Approve all outfit image prompts in one click if already reviewed in ChatGPT"):
                            approve_all_images_in_chatgpt(active_brief_id)
                            st.success("All outfit images marked as approved in ChatGPT!")
                            st.rerun()
                    else:
                        st.button("🎉 All Approved", disabled=True, use_container_width=True)

                if approved_count == total_looks:
                    st.success("🎉 All outfit images have been approved directly in ChatGPT! Stage 5 (Video Studio) is unlocked.")

                st.divider()

                # Sequential Look Navigation
                step_key = f"stage4_view_idx_{active_brief_id}"
                if step_key not in st.session_state:
                    first_unapproved = next((i for i, img in enumerate(image_assets) if img.get("approval_status") != "APPROVED"), 0)
                    st.session_state[step_key] = first_unapproved

                current_idx = min(st.session_state[step_key], total_looks - 1)

                look_options = [
                    f"Look {i + 1}: {img.get('outfit_id')} ({'✅ Approved' if img.get('approval_status') == 'APPROVED' else '⏳ Pending'})"
                    for i, img in enumerate(image_assets)
                ]
                selected_look_str = st.selectbox(
                    "Navigate Outfits / Current Look:",
                    options=look_options,
                    index=current_idx,
                    key=f"look_selector_{active_brief_id}",
                )
                selected_idx = look_options.index(selected_look_str)
                st.session_state[step_key] = selected_idx
                active_img = image_assets[selected_idx]

                img_id = active_img.get("image_id")
                oid = active_img.get("outfit_id")
                char_id = active_img.get("character_id")
                char_name = active_img.get("character_name", char_id)
                status = active_img.get("approval_status", "PENDING")
                is_approved = status == "APPROVED"
                status_color = "green" if is_approved else "orange"

                with st.container(border=True):
                    head_l, head_r = st.columns([3, 1])
                    with head_l:
                        st.markdown(f"### Look {selected_idx + 1} of {total_looks}: {oid} — {char_name}")
                        st.caption(f"Asset ID: `{img_id}` · Character ID: `{char_id}`")
                    with head_r:
                        badge_text = "APPROVED (ChatGPT Direct)" if (is_approved and active_img.get("provider") == "CHATGPT_DIRECT") else status
                        st.markdown(f":{status_color}[**{badge_text}**]")

                    p_data = active_img.get("prompt_data", {})
                    chatgpt_text = p_data.get("chatgpt_prompt") or p_data.get("prompt_text", "")

                    col_char, col_main = st.columns([1, 2])

                    with col_char:
                        st.markdown("**1. Master Reference Image**")
                        ref_rel = active_img.get("reference_image", "")
                        ref_full = (PROJECT_DIR / ref_rel).resolve() if ref_rel else None
                        if ref_full and ref_full.is_file():
                            st.image(str(ref_full), caption=f"{char_name} ({char_id})", use_container_width=True)
                            st.caption("👉 Attach this image to your message in ChatGPT.")
                        else:
                            st.warning(f"Reference image missing at: {ref_rel}")

                    with col_main:
                        st.markdown("**2. Copy Prompt to ChatGPT**")
                        st.caption("Paste this prompt into ChatGPT with the reference image attached:")
                        st.code(chatgpt_text, language="text")

                        st.markdown("**3. Confirm & Advance**")
                        act_col1, act_col2 = st.columns([2, 1])

                        with act_col1:
                            btn_label = "✅ Approved in ChatGPT → Next Look" if selected_idx < total_looks - 1 else "✅ Approved in ChatGPT (Final Look)"
                            if st.button(btn_label, key=f"appr_btn_{img_id}", type="primary", use_container_width=True):
                                approve_image_in_chatgpt(active_brief_id, img_id)
                                if selected_idx < total_looks - 1:
                                    st.session_state[step_key] = selected_idx + 1
                                st.success(f"{oid} marked as approved in ChatGPT!")
                                st.rerun()

                        with act_col2:
                            if is_approved:
                                if st.button("Reset Approval", key=f"reset_btn_{img_id}", use_container_width=True):
                                    reject_image(active_brief_id, img_id, reason="User requested revision.")
                                    st.rerun()
                            else:
                                if st.button("Skip to Next", key=f"skip_btn_{img_id}", use_container_width=True):
                                    if selected_idx < total_looks - 1:
                                        st.session_state[step_key] = selected_idx + 1
                                        st.rerun()

                        # Optional local file attachment for archival (not required)
                        with st.expander("📁 Optional: Attach Local Image File (Not Required)", expanded=False):
                            st.caption("Wear & Wonder does not require local image files. Upload only if you wish to archive a copy locally.")
                            opt_upload = st.file_uploader(f"Upload local copy for {img_id}", type=["png", "jpg", "jpeg", "webp"], key=f"opt_upload_{img_id}")
                            if opt_upload:
                                if st.button(f"Save Local File for {img_id}", key=f"btn_save_opt_{img_id}"):
                                    import_generated_image(
                                        brief_id=active_brief_id,
                                        image_id=img_id,
                                        image_bytes=opt_upload.getvalue(),
                                        file_extension="." + opt_upload.name.rsplit(".", 1)[-1].lower(),
                                    )
                                    st.success("Optional local image file attached!")
                                    st.rerun()

                            file_p = active_img.get("file_path")
                            if file_p:
                                full_p = (PROJECT_DIR / file_p).resolve()
                                if full_p.is_file():
                                    st.image(str(full_p), caption=f"Archived local file: {img_id}", width=200)

                # Overview accordion for all looks
                with st.expander("📋 Overview of All Outfit Prompts", expanded=False):
                    for idx, look in enumerate(image_assets):
                        l_id = look.get("image_id")
                        l_oid = look.get("outfit_id")
                        l_stat = look.get("approval_status", "PENDING")
                        l_col1, l_col2, l_col3 = st.columns([1, 3, 1])
                        with l_col1:
                            st.write(f"**Look {idx + 1}: {l_oid}**")
                        with l_col2:
                            st.caption(look.get("prompt_data", {}).get("chatgpt_prompt", "")[:120] + "...")
                        with l_col3:
                            if l_stat == "APPROVED":
                                st.markdown(":green[**Approved**]")
                            else:
                                if st.button(f"Approve {l_oid}", key=f"quick_appr_{l_id}"):
                                    approve_image_in_chatgpt(active_brief_id, l_id)
                                    st.rerun()


# --------------------------------------------------
# TAB 5: VIDEO STUDIO (Stage 5)
# --------------------------------------------------
with tab_videos:
    st.subheader("Stage 5: Video Prompts, Motion & Google Flow Handoff")
    st.write("Generate video prompts with motion and dialogue, import generated clips, and review clip playback.")

    if not active_brief_id:
        st.warning("Please select an active project brief in the sidebar first.")
    else:
        can_proceed, reason = can_proceed_to_stage(active_brief_id, WorkflowStage.STAGE_5_VIDEOS)
        if not can_proceed:
            st.warning(f"🔒 {reason}")
        else:
            video_assets = load_video_assets(active_brief_id)

            if st.button("🎬 Prepare Video Prompts for Approved Images", type="primary"):
                try:
                    v_assets = prepare_video_prompts(active_brief_id)
                    st.success(f"Prepared {len(v_assets)} video prompts!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not prepare video prompts: {exc}")

            st.divider()

            if video_assets:
                for vid in video_assets:
                    clip_id = vid.get("clip_id")
                    oid = vid.get("outfit_id")
                    img_id = vid.get("approved_image_id")
                    status = vid.get("approval_status", "PENDING")
                    status_color = "green" if status == "APPROVED" else ("red" if status == "REJECTED" else "orange")

                    with st.container(border=True):
                        col_vh, col_vs = st.columns([4, 1])
                        with col_vh:
                            st.markdown(f"#### {clip_id} — {oid}")
                            st.caption(f"Approved Image Asset: `{img_id}` · Character: **{vid.get('character_id')}**")
                        with col_vs:
                            st.markdown(f":{status_color}[**{status}**]")

                        st.info(f"💡 In Google Flow, upload your approved ChatGPT image for **{oid}** as the Start Frame, then paste the master prompt below.")

                        p_data = vid.get("prompt_data", {})
                        st.markdown(f"**Dialogue Line:** *\"{p_data.get('dialogue', '')}\"*")
                        st.caption(f"Speaker: {p_data.get('speaker_identity', '')} · Lip-sync: {p_data.get('lip_sync_instructions', '')}")

                        with st.expander("Google Flow Master Prompt & Settings", expanded=False):
                            st.code(p_data.get("master_prompt", ""), language="text")
                            st.write(f"**Camera Framing:** {p_data.get('camera_framing', '')} · {p_data.get('camera_movement', '')}")
                            st.write(f"**Character Staging:** {p_data.get('character_position', '')}")
                            st.write(f"**Motion & Pose:** {p_data.get('pose_and_movement', '')}")
                            st.caption(f"Duration: {p_data.get('duration_seconds', 6)}s · Aspect Ratio: {p_data.get('aspect_ratio', '9:16')}")

                        # Video Playback / Upload Section
                        col_vplay, col_vup = st.columns([1, 1])
                        file_path = vid.get("file_path")

                        with col_vplay:
                            st.markdown("**Clip Playback Preview**")
                            if file_path:
                                full_vp = (PROJECT_DIR / file_path).resolve()
                                if full_vp.is_file():
                                    st.video(str(full_vp))
                                else:
                                    st.warning(f"Video file missing at: {file_path}")
                            else:
                                st.info("No video clip imported yet. Upload or import below.")

                        with col_vup:
                            st.markdown("**Google Flow / Video Asset Import**")
                            st.caption("Upload video clip generated from Google Flow / Sora / Runway:")
                            uploaded_vid = st.file_uploader(
                                f"Upload Video Clip for {clip_id}",
                                type=["mp4", "mov", "webm"],
                                key=f"upload_vid_{clip_id}",
                            )
                            if uploaded_vid:
                                if st.button(f"Save Clip for {clip_id}", key=f"btn_save_vid_{clip_id}", type="primary"):
                                    import_generated_video(
                                        brief_id=active_brief_id,
                                        clip_id=clip_id,
                                        video_bytes=uploaded_vid.getvalue(),
                                        file_extension="." + uploaded_vid.name.rsplit(".", 1)[-1].lower(),
                                    )
                                    st.success(f"Video clip saved for {clip_id}!")
                                    st.rerun()

                            st.divider()
                            st.markdown("**Clip Approval Actions**")
                            vb1, vb2 = st.columns(2)
                            with vb1:
                                if status == "APPROVED":
                                    st.button("Approved", key=f"appr_vid_dis_{clip_id}", disabled=True, use_container_width=True)
                                elif st.button("Approve Clip", key=f"appr_vid_{clip_id}", type="primary", use_container_width=True, disabled=not bool(file_path)):
                                    try:
                                        approve_video_clip(active_brief_id, clip_id)
                                        st.success(f"{clip_id} approved!")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(str(exc))
                            with vb2:
                                if st.button("Reject Clip", key=f"rej_vid_{clip_id}", use_container_width=True):
                                    reject_video_clip(active_brief_id, clip_id, reason="User rejected video output.")
                                    st.rerun()
            else:
                st.info("No video prompts prepared yet. Click 'Prepare Video Prompts for Approved Images' above.")


# --------------------------------------------------
# TAB 6: MASTER MODEL LIBRARY (Preserved)
# --------------------------------------------------
with tab_models:
    st.subheader("Master Model Library")
    st.write("Register your reference images and identity rules. New or updated model profiles require your approval.")

    if "model_action_message" in st.session_state:
        st.success(st.session_state.pop("model_action_message"))

    model_labels = {
        "WW-CHAR-01": "Female Model 01",
        "WW-CHAR-02": "Female Model 02",
        "WW-CHAR-03": "Male Model 01",
    }

    try:
        profiles = load_models()
    except (ValueError, OSError) as exc:
        st.error(f"Could not load the model library: {exc}")
        profiles = []

    profile_by_id = {
        profile["model_id"]: profile
        for profile in profiles
        if profile.get("model_id") in ALLOWED_MODELS
    }

    st.markdown("### Registered models")

    if not profiles:
        st.info("No models registered yet. Upload your first reference image below.")

    for profile in profiles:
        model_id = profile.get("model_id")
        if model_id not in ALLOWED_MODELS:
            continue

        with st.container(border=True):
            st.markdown(f"**{profile.get('display_name', 'Unnamed model')}**")
            st.caption(model_id)

            status = profile.get("approval_status", "PENDING_APPROVAL")
            st.write("**Approval status:**", status)

            st.write("**Fixed identity characteristics:**", profile.get("identity_notes") or "Not provided")
            st.write("**Hair styling rules:**", profile.get("hair_rules") or "Not provided")

            relative_path = profile.get("reference_image", "")
            image_path = (PROJECT_DIR / relative_path).resolve()

            try:
                image_path.relative_to(PROJECT_DIR.resolve())
                path_is_inside_project = True
            except ValueError:
                path_is_inside_project = False

            if (
                path_is_inside_project
                and image_path.is_file()
                and image_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ):
                st.image(str(image_path), caption=profile.get("display_name", "Master reference"), use_container_width=True)
            else:
                st.warning("The reference image could not be found. Upload it again using the form below.")

            approve_col, pending_col = st.columns(2)
            with approve_col:
                if status == "APPROVED":
                    st.button("Already approved", key=f"approved_disabled_{model_id}", disabled=True, use_container_width=True)
                elif st.button("Approve model", key=f"approve_{model_id}", type="primary", use_container_width=True):
                    try:
                        updated = set_model_approval(model_id, True)
                        st.session_state["model_action_message"] = f"{updated['display_name']} is now APPROVED."
                        st.rerun()
                    except (ValueError, OSError) as exc:
                        st.error(f"Could not approve model: {exc}")

            with pending_col:
                if status == "PENDING_APPROVAL":
                    st.button("Already pending", key=f"pending_disabled_{model_id}", disabled=True, use_container_width=True)
                elif st.button("Return to pending", key=f"pending_{model_id}", use_container_width=True):
                    try:
                        updated = set_model_approval(model_id, False)
                        st.session_state["model_action_message"] = f"{updated['display_name']} is now pending approval."
                        st.rerun()
                    except (ValueError, OSError) as exc:
                        st.error(f"Could not update model: {exc}")

    st.divider()
    st.markdown("### Add or update a model")

    with st.form("model_form"):
        selected_model_id = st.selectbox(
            "Model ID",
            list(ALLOWED_MODELS.keys()),
            format_func=lambda item: f"{item} — {model_labels[item]}",
        )
        existing = profile_by_id.get(selected_model_id, {})

        display_name = st.text_input("Display name", value=existing.get("display_name", model_labels[selected_model_id]))
        identity_notes = st.text_area(
            "Fixed identity characteristics",
            value=existing.get("identity_notes", ""),
            placeholder="Describe face, hairline, natural hair color, texture and body proportions.",
        )
        hair_rules = st.text_area(
            "Hair styling rules",
            value=existing.get("hair_rules", ""),
            placeholder="Describe fixed hair identity and approved styling variations.",
        )
        uploaded_image = st.file_uploader(
            "Upload full-body master reference",
            type=["png", "jpg", "jpeg", "webp"],
            key="master_model_upload",
        )
        st.caption("Replacing a model image resets its approval status to pending.")

        save_model_button = st.form_submit_button("Save model profile", type="primary", use_container_width=True)

    if save_model_button:
        if not display_name.strip():
            st.error("Please enter a display name.")
        elif uploaded_image is None:
            st.error("Please upload the full-body reference image.")
        else:
            try:
                profile = save_model(
                    model_id=selected_model_id,
                    display_name=display_name,
                    identity_notes=identity_notes,
                    hair_rules=hair_rules,
                    image_bytes=uploaded_image.getvalue(),
                    image_extension="." + uploaded_image.name.rsplit(".", 1)[-1].lower(),
                )
                st.session_state["model_action_message"] = f"{profile['display_name']} saved. Status: PENDING_APPROVAL."
                st.rerun()
            except (ValueError, TypeError, OSError) as exc:
                st.error(f"Could not save model: {exc}")


# --------------------------------------------------
# TAB 7: WORKFLOW STATUS & AUDIT TRAIL
# --------------------------------------------------
with tab_status:
    st.subheader("Stage & Workflow Gate Status")
    st.write("Track end-to-end completion of prerequisite gates and view the tamper-proof audit trail.")

    if not active_brief_id:
        st.info("Select or create a brief to view its workflow gate status.")
    else:
        prereqs = get_workflow_prerequisites(active_brief_id)
        current_brief = get_brief_by_id(active_brief_id) or {}

        # Pipeline visualizer
        st.markdown("### Pipeline Gate Matrix")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("1. Idea Brief", "COMPLETED", delta="Ready")
        with c2:
            res_val = "APPROVED" if prereqs["research_approved"] else ("DONE" if prereqs["research_completed"] else "PENDING")
            st.metric("2. Research", res_val, delta="Ready" if prereqs["research_approved"] else "Gate Lock")
        with c3:
            out_val = "APPROVED" if prereqs["outfits_approved"] else ("DONE" if prereqs["has_outfits"] else "PENDING")
            st.metric("3. Outfits", out_val, delta="Ready" if prereqs["outfits_approved"] else "Gate Lock")
        with c4:
            img_val = "APPROVED" if prereqs["images_approved"] else ("DONE" if prereqs["images_generated"] else "PENDING")
            st.metric("4. Images", img_val, delta="Ready" if prereqs["images_approved"] else "Gate Lock")
        with c5:
            vid_val = "APPROVED" if prereqs["videos_approved"] else ("DONE" if prereqs["videos_generated"] else "PENDING")
            st.metric("5. Video Clips", vid_val, delta="Ready" if prereqs["videos_approved"] else "Gate Lock")

        st.divider()

        if prereqs["stage_6_ready"]:
            st.success("✨ ALL PREREQUISITES MET. Brief is certified and ready for Stage 6: Video Editing & Assembly.")
        else:
            st.warning("⚠️ Pending approvals required before video editing assembly.")

        # Audit history log
        st.markdown("### Workflow Audit Trail")
        audit_events = load_audit_events(active_brief_id)
        if audit_events:
            for ev in reversed(audit_events[-20:]):
                with st.container(border=True):
                    col_ea, col_et = st.columns([3, 1])
                    with col_ea:
                        st.markdown(f"**{ev.get('action', 'ACTION')}** (`{ev.get('stage', 'WORKFLOW')}`)")
                        st.write(ev.get("details", ""))
                        if ev.get("from_status") or ev.get("to_status"):
                            st.caption(f"Transition: `{ev.get('from_status')}` ➔ `{ev.get('to_status')}`")
                    with col_et:
                        st.caption(ev.get("timestamp", "")[:19].replace("T", " "))
        else:
            st.caption("No audit events recorded for this brief yet.")

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.divider()
st.caption("Wear & Wonder · Multi-Stage Fashion Content Automation · Stages 1–5 Complete · Approval Required")
