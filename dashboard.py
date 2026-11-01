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
    approve_image,
    configure_dual_model_image_look,
    import_generated_image,
    import_image_from_path,
    prepare_image_prompts,
    reject_image,
    update_image_visual_description,
)
from app.video_generation import (
    approve_video_clip,
    build_video_prompt_for_outfit,
    import_generated_video,
    import_video_from_path,
    prepare_video_prompts,
    regenerate_single_video_prompt,
    reject_video_clip,
)
from app.model_library import (
    ALLOWED_MODELS,
    load_models,
    save_model,
    set_model_approval,
)
from app.research import execute_fashion_research
from app.publishing import (
    approve_and_schedule_video,
    check_instagram_auth_status,
    check_youtube_auth_status,
    get_or_create_publishing_record,
    import_assembled_video,
    import_custom_thumbnail,
    record_manual_publication,
    refresh_publishing_metadata,
    set_master_image_as_thumbnail,
    update_publishing_metadata,
)
from app.storage import (
    get_brief_by_id,
    get_research_data,
    load_all_briefs,
    load_audit_events,
    load_image_assets,
    load_outfits,
    load_publishing_record,
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
        pub_rec = load_publishing_record(active_brief_id)
        pub_status = pub_rec.get("status") if pub_rec else "PENDING"
        is_published = pub_status in ("SCHEDULED", "PUBLISHED")
        status_pill(
            "6. Publishing",
            is_published,
            pub_status if is_published else ("READY" if prereqs["stage_6_ready"] else "LOCKED"),
        )

        st.divider()
        if is_published:
            st.success(f"🚀 Video is {pub_status} across platforms!")
        elif prereqs["stage_6_ready"]:
            st.success("🎉 All assets approved! Ready for Stage 6: Video Editing & Publishing.")
        else:
            st.info("🔒 Stage 6 Publishing locked until all clips are approved.")


# --------------------------------------------------
# MAIN WORKSPACE TABS
# --------------------------------------------------
tab_idea, tab_research, tab_outfits, tab_images, tab_videos, tab_publishing, tab_models, tab_status = st.tabs([
    "💡 Idea Studio",
    "🔎 Research",
    "👗 Outfit Proposals",
    "📸 Image Studio",
    "🎬 Video Studio",
    "🚀 Stage 6: Publishing",
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
# TAB 4: IMAGE STUDIO (Stage 4: Generation, Upload & Verification)
# --------------------------------------------------
with tab_images:
    st.subheader("Stage 4: Image Studio & Visual Verification")
    st.write(
        "Generate each look in ChatGPT using your master model reference, upload the generated image, "
        "review/verify the extracted visual details, and give your explicit approval."
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
                # Count looks that are approved AND have file existing on disk
                verified_approved_count = 0
                for img in image_assets:
                    fp = img.get("file_path")
                    if img.get("approval_status") == "APPROVED" and fp and (PROJECT_DIR / fp).is_file():
                        verified_approved_count += 1

                # Top Progress & Quick-Action Bar
                top_col1, top_col2 = st.columns([3, 1])
                with top_col1:
                    st.progress(
                        verified_approved_count / total_looks,
                        text=f"Stage 4 Progress: {verified_approved_count} of {total_looks} looks verified & approved on disk",
                    )
                with top_col2:
                    st.link_button("🚀 Open ChatGPT", "https://chatgpt.com", use_container_width=True)

                if verified_approved_count == total_looks:
                    st.success("🎉 All outfit images have been uploaded, verified, and approved on disk! Stage 5 (Video Studio) is unlocked.")

                st.divider()

                # Sequential Look Navigation
                step_key = f"stage4_view_idx_{active_brief_id}"
                if step_key not in st.session_state:
                    first_unapproved = next(
                        (i for i, img in enumerate(image_assets) if img.get("approval_status") != "APPROVED" or not img.get("file_path")),
                        0,
                    )
                    st.session_state[step_key] = first_unapproved

                current_idx = min(st.session_state[step_key], total_looks - 1)

                look_options = []
                for i, img in enumerate(image_assets):
                    fp = img.get("file_path")
                    has_file = bool(fp and (PROJECT_DIR / fp).is_file())
                    is_appr = img.get("approval_status") == "APPROVED" and has_file
                    status_label = "✅ Approved" if is_appr else ("📷 File Uploaded" if has_file else "⏳ Needs Upload")
                    look_options.append(f"Look {i + 1}: {img.get('outfit_id')} ({status_label})")

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
                file_rel = active_img.get("file_path")
                full_img_p = (PROJECT_DIR / file_rel).resolve() if file_rel else None
                file_exists = bool(full_img_p and full_img_p.is_file())
                is_approved = status == "APPROVED" and file_exists
                p_version = active_img.get("prompt_version", 1)

                with st.container(border=True):
                    head_l, head_r = st.columns([3, 1])
                    with head_l:
                        st.markdown(f"### Look {selected_idx + 1} of {total_looks}: {oid} — {char_name}")
                        st.caption(f"Asset ID: `{img_id}` · Character ID: `{char_id}` · Prompt Version: `v{p_version}`")
                    with head_r:
                        if is_approved:
                            st.markdown(":green[**APPROVED & VERIFIED**]")
                        elif file_exists:
                            st.markdown(":orange[**FILE UPLOADED (PENDING APPROVAL)**]")
                        else:
                            st.markdown(":red[**AWAITING IMAGE UPLOAD**]")

                    # Two-Model Wardrobe Studio Mode Expander
                    is_dual = active_img.get("is_dual_model", False)
                    with st.expander("👯 Two-Model Wardrobe Studio (Generate Both Models in Stylish Wardrobe)", expanded=is_dual):
                        st.caption(
                            "Select two master models and generate ONE image containing both models together in a stylish wardrobe/dressing-room background. "
                            "In Stage 5, Model 1 will be the only speaker with lip-sync, while Model 2 remains completely silent."
                        )
                        dm_col1, dm_col2 = st.columns(2)
                        available_chars = list(ALLOWED_MODELS.keys())
                        all_outfits = load_outfits(active_brief_id)
                        approved_oids = [o["outfit_id"] for o in all_outfits if o.get("approval_status") == "APPROVED"] or [oid]

                        with dm_col1:
                            m1_idx = available_chars.index(char_id) if char_id in available_chars else 0
                            sel_m1 = st.selectbox("Select Model 1 (Primary Speaker):", options=available_chars, index=m1_idx, key=f"sel_m1_{img_id}")
                            o1_idx = approved_oids.index(oid) if oid in approved_oids else 0
                            sel_o1 = st.selectbox("Select Outfit for Model 1:", options=approved_oids, index=o1_idx, key=f"sel_o1_{img_id}")
                        with dm_col2:
                            current_m2 = active_img.get("dual_character_id")
                            m2_default = current_m2 if (current_m2 and current_m2 in available_chars) else next((c for c in available_chars if c != sel_m1), available_chars[0])
                            m2_idx = available_chars.index(m2_default)
                            sel_m2 = st.selectbox("Select Model 2 (Silent Companion):", options=available_chars, index=m2_idx, key=f"sel_m2_{img_id}")
                            sel_o2 = st.selectbox("Select Outfit for Model 2:", options=approved_oids, index=min(1, len(approved_oids) - 1), key=f"sel_o2_{img_id}")

                        if st.button("✨ Apply Two-Model Wardrobe Prompt to this Look", key=f"btn_apply_dual_{img_id}", type="primary"):
                            configure_dual_model_image_look(
                                brief_id=active_brief_id,
                                image_id=img_id,
                                character_id_1=sel_m1,
                                character_id_2=sel_m2,
                                outfit_id_1=sel_o1,
                                outfit_id_2=sel_o2,
                            )
                            st.success("Two-model wardrobe prompt applied! Review prompt and reference images below.")
                            st.rerun()

                    p_data = active_img.get("prompt_data", {})
                    chatgpt_text = p_data.get("chatgpt_prompt") or p_data.get("prompt_text", "")

                    # 3-Column Studio Layout
                    col_ref, col_upload, col_verify = st.columns([1.1, 1, 1.2])

                    # Column 1: Reference & ChatGPT Prompt
                    with col_ref:
                        if is_dual:
                            st.markdown("**1. Master Character References (Both Models)**")
                            st.info("👥 **Attach BOTH reference images** to your message in ChatGPT.")
                            r_c1, r_c2 = st.columns(2)
                            ref_rel1 = active_img.get("reference_image", "")
                            ref_full1 = (PROJECT_DIR / ref_rel1).resolve() if ref_rel1 else None
                            with r_c1:
                                if ref_full1 and ref_full1.is_file():
                                    st.image(str(ref_full1), caption=f"Model 1: {active_img.get('character_id')}", use_container_width=True)
                            ref_rel2 = active_img.get("reference_image_2", "")
                            ref_full2 = (PROJECT_DIR / ref_rel2).resolve() if ref_rel2 else None
                            with r_c2:
                                if ref_full2 and ref_full2.is_file():
                                    st.image(str(ref_full2), caption=f"Model 2: {active_img.get('dual_character_id')}", use_container_width=True)

                            st.markdown("**Prompt for ChatGPT (Two Models in Wardrobe)**")
                            st.caption("Paste into ChatGPT with BOTH master reference photos attached:")
                            st.code(chatgpt_text, language="text")
                        else:
                            st.markdown("**1. Master Character Reference**")
                            ref_rel = active_img.get("reference_image", "")
                            ref_full = (PROJECT_DIR / ref_rel).resolve() if ref_rel else None
                            if ref_full and ref_full.is_file():
                                st.image(str(ref_full), caption=f"{char_name} ({char_id})", use_container_width=True)
                                st.caption("👉 Attach this master model photo to ChatGPT.")
                            else:
                                st.warning(f"Reference image missing at: {ref_rel}")

                            st.markdown("**Prompt for ChatGPT**")
                            st.caption("Paste into ChatGPT with the reference image attached:")
                            st.code(chatgpt_text, language="text")

                    # Column 2: Upload Generated Image
                    with col_upload:
                        st.markdown("**2. Upload ChatGPT Generated Image**")
                        upload_caption = f"Upload the image generated from ChatGPT containing both models for {oid}:" if is_dual else f"Upload the image generated from ChatGPT for {oid}:"
                        st.caption(upload_caption)
                        uploaded_file = st.file_uploader(
                            f"Drop ChatGPT image for {oid}",
                            type=["png", "jpg", "jpeg", "webp"],
                            key=f"file_uploader_{img_id}",
                        )
                        if uploaded_file:
                            if st.button(f"📥 Save & Ingest Image for {oid}", key=f"btn_save_img_{img_id}", type="primary"):
                                ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
                                import_generated_image(
                                    brief_id=active_brief_id,
                                    image_id=img_id,
                                    image_bytes=uploaded_file.getvalue(),
                                    file_extension=ext,
                                )
                                st.success(f"Image ingested and associated with {oid}!")
                                st.rerun()

                        if file_exists:
                            st.image(str(full_img_p), caption=f"Current Outfit Image ({full_img_p.name})", use_container_width=True)
                            st.caption(f"📁 Path: `{file_rel}`")
                        else:
                            st.info("⚠️ No image file uploaded yet for this look. Upload above to unlock approval.")

                    # Column 3: Visual Description & Approval Gate
                    with col_verify:
                        st.markdown("**3. Visual Inspection & Baseline**")
                        st.caption("Extracted and verified visual details matching this outfit:")

                        vdesc = active_img.get("visual_description", {})
                        with st.form(key=f"vdesc_form_{img_id}"):
                            vd_clothing = st.text_input("Clothing & Garments", value=vdesc.get("clothing", ""))
                            vd_colours = st.text_input("Colours & Palette", value=vdesc.get("colours", ""))
                            vd_fit = st.text_input("Fit & Silhouette", value=vdesc.get("fit", ""))
                            vd_footwear = st.text_input("Footwear", value=vdesc.get("footwear", ""))
                            vd_accessories = st.text_input("Accessories & Bags", value=vdesc.get("accessories", ""))
                            vd_hairstyle = st.text_input("Hairstyle & Grooming", value=vdesc.get("hairstyle", ""))
                            vd_background = st.text_input("Background & Setting", value=vdesc.get("background", ""))
                            vd_pose = st.text_input("Pose & Staging", value=vdesc.get("pose", ""))

                            save_vd_btn = st.form_submit_button("💾 Update Visual Description")
                            if save_vd_btn:
                                updated_vd = {
                                    "clothing": vd_clothing,
                                    "colours": vd_colours,
                                    "fit": vd_fit,
                                    "footwear": vd_footwear,
                                    "accessories": vd_accessories,
                                    "hairstyle": vd_hairstyle,
                                    "background": vd_background,
                                    "pose": vd_pose,
                                }
                                update_image_visual_description(active_brief_id, img_id, updated_vd)
                                st.success("Visual description updated!")
                                st.rerun()

                        st.markdown("**4. Approval Gate**")
                        if not file_exists:
                            st.button(
                                "🔒 Approve Outfit Image (Upload Required)",
                                key=f"btn_appr_dis_{img_id}",
                                disabled=True,
                                use_container_width=True,
                                help="Upload the generated image file before approving.",
                            )
                        elif is_approved:
                            st.success("✅ Look Approved and Ready for Stage 5 Video Studio!")
                            act1, act2 = st.columns(2)
                            with act1:
                                if selected_idx < total_looks - 1:
                                    if st.button("Next Look ➡️", key=f"btn_next_{img_id}", use_container_width=True):
                                        st.session_state[step_key] = selected_idx + 1
                                        st.rerun()
                            with act2:
                                if st.button("Reset Approval", key=f"btn_reset_{img_id}", use_container_width=True):
                                    reject_image(active_brief_id, img_id, reason="User requested revision.")
                                    st.rerun()
                        else:
                            btn_label = "✅ Approve Look & Proceed" if selected_idx < total_looks - 1 else "✅ Approve Final Look"
                            if st.button(btn_label, key=f"btn_appr_{img_id}", type="primary", use_container_width=True):
                                try:
                                    approve_image(active_brief_id, img_id)
                                    if selected_idx < total_looks - 1:
                                        st.session_state[step_key] = selected_idx + 1
                                    st.success(f"{oid} image verified and approved!")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Approval failed: {exc}")

                # Overview accordion for all looks
                with st.expander("📋 Overview of All Outfit Images & Verification Status", expanded=False):
                    for idx, look in enumerate(image_assets):
                        l_id = look.get("image_id")
                        l_oid = look.get("outfit_id")
                        l_fp = look.get("file_path")
                        l_has_f = bool(l_fp and (PROJECT_DIR / l_fp).is_file())
                        l_stat = look.get("approval_status", "PENDING")
                        l_is_appr = l_stat == "APPROVED" and l_has_f

                        l_col1, l_col2, l_col3 = st.columns([1, 2, 1])
                        with l_col1:
                            st.write(f"**Look {idx + 1}: {l_oid}**")
                            st.caption(f"Char: `{look.get('character_id')}` · v{look.get('prompt_version', 1)}")
                        with l_col2:
                            if l_has_f:
                                st.caption(f"📁 `{l_fp}`")
                            else:
                                st.caption("⚠️ No image file uploaded")
                        with l_col3:
                            if l_is_appr:
                                st.markdown(":green[**Approved & Verified**]")
                            elif l_has_f:
                                st.markdown(":orange[**Pending Approval**]")
                            else:
                                st.markdown(":red[**Missing Upload**]")


# --------------------------------------------------
# TAB 5: VIDEO STUDIO (Stage 5)
# --------------------------------------------------
with tab_videos:
    st.subheader("Stage 5: Video Prompts, Motion & Google Flow Handoff")
    st.write(
        "Generate Google Flow video prompts strictly matching your approved Stage 4 outfit images. "
        "Each prompt uses your approved image as the Starting Frame, preserving exact wardrobe, colors, motion, and lip-sync."
    )

    if not active_brief_id:
        st.warning("Please select an active project brief in the sidebar first.")
    else:
        can_proceed, reason = can_proceed_to_stage(active_brief_id, WorkflowStage.STAGE_5_VIDEOS)
        if not can_proceed:
            st.warning(f"🔒 {reason}")
        else:
            video_assets = load_video_assets(active_brief_id)

            if not video_assets:
                st.info("Stage 4 outfit images are approved and verified on disk! Prepare video prompts below.")
                if st.button("🎬 Prepare Video Prompts for Approved Images", type="primary"):
                    try:
                        v_assets = prepare_video_prompts(active_brief_id)
                        st.success(f"Prepared {len(v_assets)} video prompts!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not prepare video prompts: {exc}")
            else:
                # Top Refresh / Re-align all button
                vtop_col1, vtop_col2 = st.columns([3, 1])
                with vtop_col1:
                    st.write(f"**{len(video_assets)} Video Clip Prompts Prepared**")
                with vtop_col2:
                    if st.button("🔄 Regenerate All Video Prompts", help="Re-align all video prompts with current Stage 4 approved images"):
                        try:
                            prepare_video_prompts(active_brief_id)
                            st.success("All video prompts regenerated from approved images!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Regeneration failed: {exc}")

                st.divider()

                # Load image assets dictionary for quick reference lookups
                images_list = load_image_assets(active_brief_id)
                images_by_id = {img.get("image_id"): img for img in images_list}

                for vid in video_assets:
                    clip_id = vid.get("clip_id")
                    oid = vid.get("outfit_id")
                    img_id = vid.get("approved_image_id")
                    status = vid.get("approval_status", "PENDING")
                    is_outdated = vid.get("is_outdated", False)
                    status_color = "green" if status == "APPROVED" else ("red" if status == "REJECTED" else "orange")

                    # Look up corresponding Stage 4 image asset
                    matched_img = images_by_id.get(img_id, {})
                    img_rel_path = matched_img.get("file_path")
                    full_img_p = (PROJECT_DIR / img_rel_path).resolve() if img_rel_path else None
                    has_start_frame = bool(full_img_p and full_img_p.is_file())

                    with st.container(border=True):
                        col_vh, col_vs = st.columns([4, 1])
                        with col_vh:
                            st.markdown(f"#### {clip_id} — {oid}")
                            st.caption(f"Approved Stage 4 Asset: `{img_id}` · Character: **{vid.get('character_id')}**")
                        with col_vs:
                            if is_outdated:
                                st.markdown(":red[**OUTDATED**]")
                            else:
                                st.markdown(f":{status_color}[**{status}**]")

                        if is_outdated:
                            st.warning(
                                "⚠️ The Stage 4 image for this outfit was updated or re-uploaded. "
                                "This video prompt is outdated. Click below to regenerate and re-align with the new image."
                            )
                            if st.button(f"🔄 Re-align Prompt for {clip_id}", key=f"btn_realign_{clip_id}", type="primary"):
                                try:
                                    regenerate_single_video_prompt(active_brief_id, clip_id)
                                    st.success(f"{clip_id} re-aligned with updated Stage 4 image!")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Re-alignment failed: {exc}")

                        p_data = vid.get("prompt_data", {})

                        # 2-Column Layout: Start Frame Handoff (Left) & Master Prompt (Right)
                        col_frame, col_prompt = st.columns([1, 2])

                        with col_frame:
                            st.markdown("**1. Google Flow Starting Frame**")
                            if has_start_frame:
                                st.image(str(full_img_p), caption=f"Start Frame: {full_img_p.name}", use_container_width=True)
                                st.caption(f"📁 Path: `{img_rel_path}`")

                                try:
                                    with open(full_img_p, "rb") as sf_file:
                                        sf_bytes = sf_file.read()
                                    st.download_button(
                                        label="⬇️ Download Starting Frame",
                                        data=sf_bytes,
                                        file_name=full_img_p.name,
                                        mime="image/png",
                                        key=f"dl_sf_{clip_id}",
                                        use_container_width=True,
                                    )
                                except Exception:
                                    pass
                                st.caption("👉 In Google Flow, set this image as the Start Frame.")
                            else:
                                st.error("⚠️ Approved image file not found on disk. Return to Stage 4 to upload.")

                        with col_prompt:
                            st.markdown("**2. Google Flow Master Prompt**")
                            st.caption("Paste this master prompt into Google Flow with the Starting Frame uploaded:")
                            st.code(p_data.get("master_prompt", ""), language="text")

                            is_dual_clip = bool(vid.get("dual_character_id") or matched_img.get("is_dual_model"))
                            if is_dual_clip:
                                st.info(
                                    f"👥 **Two-Model Wardrobe Video Directives**:\n"
                                    f"- 🗣️ **Model 1 ({vid.get('character_id')})**: The ONLY speaker. Delivers dialogue with accurate lip-sync and expressive natural gestures.\n"
                                    f"- 🤫 **Model 2 ({vid.get('dual_character_id')})**: Strictly silent, lips closed with NO mouth movement as if speaking, reacting naturally.\n"
                                    f"- 🚪 **Wardrobe Background**: Stylish dressing room interior with mirror and garment racks preserved 100% stable."
                                )

                            st.markdown(f"**Dialogue:** *\"{p_data.get('dialogue', '')}\"*")
                            st.caption(f"Speaker: {p_data.get('speaker_identity', '')} · Lip-sync: {p_data.get('lip_sync_instructions', '')}")

                            with st.expander("Camera, Motion & Continuity Details", expanded=False):
                                st.write(f"**Camera Framing:** {p_data.get('camera_framing', '')}")
                                st.write(f"**Camera Movement:** {p_data.get('camera_movement', '')}")
                                st.write(f"**Pose & Movement:** {p_data.get('pose_and_movement', '')}")
                                st.write(f"**Character Staging:** {p_data.get('character_position', '')}")
                                st.write(f"**Negative Constraints:** {p_data.get('negative_constraints', '')}")
                                st.caption(f"Duration: {p_data.get('duration_seconds', 6)}s · Aspect Ratio: {p_data.get('aspect_ratio', '9:16')} · FPS: {p_data.get('fps', 24)}")

                        st.divider()

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
                                st.info("No video clip imported yet. Upload generated clip below.")

                        with col_vup:
                            st.markdown("**Google Flow / Video Clip Import**")
                            st.caption("Upload video clip generated from Google Flow:")
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


# --------------------------------------------------
# TAB 6: STAGE 6: PUBLISHING & SCHEDULING STUDIO
# --------------------------------------------------
with tab_publishing:
    st.subheader("Stage 6: Publishing & Scheduling Studio")
    st.write(
        "Upload your final assembled 9:16 vertical Short/Reel, review platform-optimized titles, "
        "descriptions with timestamps, and schedule via official APIs or the 1-Click Publishing Kit."
    )

    if not active_brief_id:
        st.info("Select or create a brief to access Stage 6 Publishing.")
    else:
        prereqs = get_workflow_prerequisites(active_brief_id)
        pub_rec = get_or_create_publishing_record(active_brief_id)

        if not prereqs["stage_6_ready"]:
            st.warning(
                "🔒 **Prerequisite Gate Notice**: Stages 1–5 have pending approvals. "
                "You can upload your assembled video and preview draft metadata now, "
                "but publishing/scheduling requires all earlier stage assets to be approved."
            )
        else:
            st.success("✨ **Prerequisite Gates Cleared**: All outfits, images, and clips are approved! Ready for publishing.")

        # --- Section 1: Final Video & Thumbnail Intake ---
        st.markdown("### 1. Final Assembled Video & Custom Thumbnail")
        st.caption("Upload your stitched 9:16 vertical video and select or upload a high-resolution thumbnail.")

        col_vid_box, col_thumb_box = st.columns([1, 1])

        # Left Column: Assembled Video
        with col_vid_box:
            st.markdown("#### 🎬 Assembled Video (9:16 Short / Reel)")
            vid_path = pub_rec.get("video_file_path")

            if vid_path:
                full_vp = (PROJECT_DIR / vid_path).resolve()
                if full_vp.is_file():
                    st.video(str(full_vp))
                    st.caption(f"📁 **File:** `{pub_rec.get('video_filename')}` · **Size:** {pub_rec.get('video_filesize', 0) / (1024 * 1024):.2f} MB")
                else:
                    st.warning(f"Video file missing on disk at: `{vid_path}`")
            else:
                st.info("No assembled video uploaded yet. Stitched Google Flow clips can be uploaded below:")

            uploaded_assembled = st.file_uploader(
                "Upload Assembled Video (.mp4, .mov, .webm)",
                type=["mp4", "mov", "webm"],
                key=f"upload_assembled_{active_brief_id}",
            )
            if uploaded_assembled:
                if st.button("💾 Save Assembled Video", type="primary", key="btn_save_assembled_vid"):
                    import_assembled_video(
                        brief_id=active_brief_id,
                        video_bytes=uploaded_assembled.getvalue(),
                        filename=uploaded_assembled.name,
                    )
                    st.success("Assembled video saved successfully!")
                    st.rerun()

        # Right Column: Thumbnail / Cover
        with col_thumb_box:
            st.markdown("#### 🖼️ Cover / Thumbnail (9:16 Vertical)")
            thumb_path = pub_rec.get("thumbnail_file_path")

            if thumb_path:
                full_tp = (PROJECT_DIR / thumb_path).resolve()
                if full_tp.is_file():
                    st.image(str(full_tp), caption=f"Thumbnail ({pub_rec.get('thumbnail_source', 'Custom')})", use_container_width=True)
                else:
                    st.warning(f"Thumbnail file missing at `{thumb_path}`")
            else:
                st.info("No thumbnail selected yet. Choose an approved Stage 4 image or upload a custom cover.")

            thumb_tab_stage4, thumb_tab_custom = st.tabs(["Select Stage 4 Approved Image", "Upload Custom Cover"])

            with thumb_tab_stage4:
                stage4_images = [
                    img for img in load_image_assets(active_brief_id)
                    if img.get("approval_status") == ApprovalStatus.APPROVED.value
                    and img.get("file_path")
                    and (PROJECT_DIR / img["file_path"]).is_file()
                ]
                if stage4_images:
                    img_opts = {f"{img.get('image_id')} ({img.get('character_name', 'Model')}) - {img.get('outfit_id')}": img.get("image_id") for img in stage4_images}
                    selected_img_label = st.selectbox("Choose Approved Look Image", list(img_opts.keys()), key="select_s4_thumb")
                    if st.button("Use Stage 4 Image as Thumbnail", key="btn_set_s4_thumb", use_container_width=True):
                        set_master_image_as_thumbnail(active_brief_id, img_opts[selected_img_label])
                        st.success("Stage 4 approved image set as video thumbnail!")
                        st.rerun()
                else:
                    st.caption("No approved Stage 4 images with files on disk found. Upload and approve images in Stage 4 first, or upload custom cover.")

            with thumb_tab_custom:
                uploaded_thumb = st.file_uploader(
                    "Upload Custom Cover (.png, .jpg, .webp)",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"upload_custom_thumb_{active_brief_id}",
                )
                if uploaded_thumb:
                    if st.button("💾 Save Custom Thumbnail", key="btn_save_custom_thumb", use_container_width=True):
                        import_custom_thumbnail(
                            brief_id=active_brief_id,
                            image_bytes=uploaded_thumb.getvalue(),
                            filename=uploaded_thumb.name,
                        )
                        st.success("Custom thumbnail saved!")
                        st.rerun()

        st.divider()

        # --- Section 2: Platform Metadata Studio ---
        st.markdown("### 2. Platform-Specific Titles, Descriptions & SEO Tags")
        st.caption("Auto-generated based on project brief, character dialogue, approved styling, and multi-look timestamps.")

        col_meta_top, col_meta_btn = st.columns([3, 1])
        with col_meta_btn:
            if st.button("🔄 Regenerate Metadata", key="btn_refresh_publishing_meta", use_container_width=True):
                refresh_publishing_metadata(active_brief_id)
                st.success("Metadata regenerated from latest outfits!")
                st.rerun()

        meta = pub_rec.get("metadata", {})
        yt_meta = meta.get("youtube", {})
        ig_meta = meta.get("instagram", {})

        meta_tab_yt, meta_tab_ig = st.tabs(["🔴 YouTube Shorts Metadata", "📸 Instagram Reels Metadata"])

        with meta_tab_yt:
            with st.form("form_yt_metadata"):
                curr_yt_title = yt_meta.get("title", "")
                yt_title_input = st.text_input(
                    f"Title (Characters: {len(curr_yt_title)}/70 — must end with #Shorts)",
                    value=curr_yt_title,
                )
                curr_yt_desc = yt_meta.get("description", "")
                yt_desc_input = st.text_area(
                    "Description & Multi-Look Timestamps",
                    value=curr_yt_desc,
                    height=240,
                )
                curr_yt_tags = yt_meta.get("tags_comma_separated", ", ".join(yt_meta.get("tags", [])))
                yt_tags_input = st.text_area(
                    f"Search Tags (Characters: {len(curr_yt_tags)}/500)",
                    value=curr_yt_tags,
                    height=80,
                )
                st.caption("Category: **26 — Howto & Style** (Automatic)")

                if st.form_submit_button("💾 Save YouTube Metadata", type="primary"):
                    clean_tags = [t.strip() for t in yt_tags_input.split(",") if t.strip()]
                    update_publishing_metadata(
                        active_brief_id,
                        "youtube",
                        {
                            "title": yt_title_input,
                            "description": yt_desc_input,
                            "tags": clean_tags,
                            "tags_comma_separated": yt_tags_input,
                        },
                    )
                    st.success("YouTube metadata updated!")
                    st.rerun()

        with meta_tab_ig:
            with st.form("form_ig_metadata"):
                curr_ig_caption = ig_meta.get("caption", "")
                ig_caption_input = st.text_area(
                    "Instagram Caption (Hook + Look Breakdown + CTA)",
                    value=curr_ig_caption,
                    height=240,
                )
                curr_ig_hashtags = ig_meta.get("hashtags_text", " ".join(ig_meta.get("hashtags", [])))
                ig_hashtags_input = st.text_area(
                    "Curated Hashtags (Tiered: Niche, Trending & Format)",
                    value=curr_ig_hashtags,
                    height=90,
                )

                if st.form_submit_button("💾 Save Instagram Metadata", type="primary"):
                    clean_hts = [h.strip() for h in ig_hashtags_input.split() if h.strip()]
                    update_publishing_metadata(
                        active_brief_id,
                        "instagram",
                        {
                            "caption": ig_caption_input,
                            "hashtags": clean_hts,
                            "hashtags_text": ig_hashtags_input,
                        },
                    )
                    st.success("Instagram metadata updated!")
                    st.rerun()

        st.divider()

        # --- Section 3: Scheduling & Dispatch Controls ---
        st.markdown("### 3. Scheduling & Privacy Settings")
        col_plat, col_time = st.columns([1, 1])

        with col_plat:
            st.markdown("#### Destination Platforms")
            yt_checked = st.checkbox("YouTube Shorts", value=True, key="chk_yt")
            ig_checked = st.checkbox("Instagram Reels", value=True, key="chk_ig")

            privacy_status = st.selectbox(
                "YouTube Visibility",
                ["private", "public", "unlisted"],
                index=0,
                format_func=lambda s: s.capitalize() + (" (Required for scheduled publishing)" if s == "private" else ""),
                key="sel_privacy_status",
            )

        with col_time:
            st.markdown("#### Publication Timing")
            timing_choice = st.radio(
                "Choose when to publish:",
                ["Schedule for Later", "Publish Immediately"],
                key="rad_timing_choice",
            )

            scheduled_iso_str = None
            if timing_choice == "Schedule for Later":
                now_plus_day = datetime.now() + timedelta(days=1)
                sched_date = st.date_input("Scheduled Date", value=now_plus_day.date(), min_value=datetime.now().date(), key="date_sched")
                sched_time = st.time_input("Scheduled Time (Local)", value=datetime.strptime("18:00", "%H:%M").time(), key="time_sched")
                combined_local = datetime.combine(sched_date, sched_time)
                # Convert to UTC ISO string
                scheduled_iso_str = combined_local.astimezone(timezone.utc).isoformat()
                st.info(f"📅 **Scheduled for:** {combined_local.strftime('%B %d, %Y at %I:%M %p')} Local (`{scheduled_iso_str}` UTC)")

        st.divider()

        # --- Section 4: Mandatory Approval Gate & API Dispatch ---
        st.markdown("### 4. Mandatory Approval Gate & API Publishing")
        st.caption("Wear & Wonder strictly requires explicit authorization before initiating any platform publication.")

        yt_auth = check_youtube_auth_status()
        ig_auth = check_instagram_auth_status()

        col_auth1, col_auth2 = st.columns(2)
        with col_auth1:
            if yt_auth["configured"]:
                st.success(f"🟢 **YouTube API Ready:** {yt_auth['details']}")
            else:
                st.info(f"ℹ️ **YouTube API:** {yt_auth['details']}")

        with col_auth2:
            if ig_auth["configured"]:
                st.success(f"🟢 **Instagram API Ready:** {ig_auth['details']}")
            else:
                st.info(f"ℹ️ **Instagram API:** {ig_auth['details']}")

        has_video = bool(pub_rec.get("video_file_path") and (PROJECT_DIR / pub_rec["video_file_path"]).is_file())

        if not has_video:
            st.error("⚠️ **Gate Blocked**: Please upload an assembled video above before scheduling.")
        elif not prereqs["stage_6_ready"]:
            st.warning("⚠️ **Gate Warning**: Stages 1–5 have unapproved assets. Review and approve earlier stages to unlock publishing.")

        gate_confirmed = st.checkbox(
            "✅ **Mandatory Creator Approval**: I have reviewed the assembled video, custom thumbnail, "
            "dialogue lip-sync, and platform-tailored metadata with multi-look timestamps, and I authorize "
            "Wear & Wonder to schedule/publish this content.",
            key="chk_mandatory_gate",
            disabled=not has_video,
        )

        col_btn_api, col_btn_test = st.columns([2, 1])

        target_platforms = []
        if yt_checked:
            target_platforms.append("youtube")
        if ig_checked:
            target_platforms.append("instagram")

        with col_btn_api:
            btn_publish = st.button(
                "🚀 Approve & Publish / Schedule via API",
                type="primary",
                disabled=not (gate_confirmed and target_platforms),
                use_container_width=True,
                key="btn_run_api_publish",
            )
            if btn_publish:
                try:
                    res = approve_and_schedule_video(
                        brief_id=active_brief_id,
                        platforms=target_platforms,
                        scheduled_time_iso=scheduled_iso_str,
                        privacy_status=privacy_status,
                        user_name="Creator",
                        mock_mode=False,
                    )
                    st.success(f"🎉 Success! Video has been {res.get('status')} across {', '.join(target_platforms)}!")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(f"Platform API Error: {exc}")
                    st.info("💡 You can use the Zero-Setup 1-Click Publishing Kit below immediately with ₹0 and no configuration!")
                except Exception as exc:
                    st.error(f"Error: {exc}")

        with col_btn_test:
            btn_test_sim = st.button(
                "🧪 Test Integration (Sandbox Dispatch)",
                disabled=not (gate_confirmed and target_platforms),
                use_container_width=True,
                key="btn_test_sandbox",
            )
            if btn_test_sim:
                try:
                    res = approve_and_schedule_video(
                        brief_id=active_brief_id,
                        platforms=target_platforms,
                        scheduled_time_iso=scheduled_iso_str,
                        privacy_status=privacy_status,
                        user_name="Creator",
                        mock_mode=True,
                    )
                    st.success(f"🧪 Sandbox Verified! Simulated {res.get('status')} across {', '.join(target_platforms)}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        st.divider()

        # --- Section 5: Zero-Setup 1-Click Publishing Kit (Mode B) ---
        with st.container(border=True):
            st.markdown("### ⚡ Zero-Setup 1-Click Publishing Kit (Instant ₹0 / No Developer Setup)")
            st.write(
                "Don't want to configure Google Cloud or Meta developer consoles? "
                "You can publish right now for ₹0 using official web studios with our 1-click formatted kits:"
            )

            col_kit_yt, col_kit_ig = st.columns(2)

            with col_kit_yt:
                st.markdown("#### 🔴 YouTube Studio Kit")
                st.caption("1. Copy pre-formatted title, description with timestamps, and tags.\n2. Click button to open YouTube Studio upload dialog directly.")

                st.markdown("**Title:**")
                st.code(yt_meta.get("title", ""), language="text")

                st.markdown("**Description & Timestamps:**")
                st.code(yt_meta.get("description", ""), language="text")

                st.markdown("**SEO Search Tags:**")
                st.code(yt_meta.get("tags_comma_separated", ""), language="text")

                if vid_path and (PROJECT_DIR / vid_path).is_file():
                    with open(PROJECT_DIR / vid_path, "rb") as f_dl:
                        st.download_button(
                            "📥 Download Assembled Video (.mp4)",
                            data=f_dl.read(),
                            file_name=pub_rec.get("video_filename", "video.mp4"),
                            mime="video/mp4",
                            key="dl_pub_video_yt",
                            use_container_width=True,
                        )

                if thumb_path and (PROJECT_DIR / thumb_path).is_file():
                    with open(PROJECT_DIR / thumb_path, "rb") as f_tp:
                        st.download_button(
                            "📥 Download Thumbnail Cover",
                            data=f_tp.read(),
                            file_name=Path(thumb_path).name,
                            mime="image/png",
                            key="dl_pub_thumb_yt",
                            use_container_width=True,
                        )

                st.link_button(
                    "🔗 Open YouTube Studio Upload",
                    "https://studio.youtube.com/channel/UC/videos/upload?d=pt",
                    type="primary",
                    use_container_width=True,
                )

            with col_kit_ig:
                st.markdown("#### 📸 Meta Business Suite Kit")
                st.caption("1. Copy pre-formatted aesthetic caption & curated hashtags.\n2. Click button to open Meta Business Suite Reels composer directly.")

                st.markdown("**Instagram Caption & Hashtags:**")
                st.code(ig_meta.get("caption", ""), language="text")

                if vid_path and (PROJECT_DIR / vid_path).is_file():
                    with open(PROJECT_DIR / vid_path, "rb") as f_dl_ig:
                        st.download_button(
                            "📥 Download Assembled Reel (.mp4)",
                            data=f_dl_ig.read(),
                            file_name=pub_rec.get("video_filename", "reel.mp4"),
                            mime="video/mp4",
                            key="dl_pub_video_ig",
                            use_container_width=True,
                        )

                st.link_button(
                    "🔗 Open Meta Business Suite Reels Composer",
                    "https://business.facebook.com/latest/reels_composer",
                    type="primary",
                    use_container_width=True,
                )

            st.divider()
            with st.expander("📝 Record Manual Publication in Audit Log", expanded=False):
                st.write("If you uploaded or scheduled directly through YouTube Studio or Meta Business Suite, record your live link here:")
                with st.form("form_manual_record"):
                    man_plat = st.selectbox("Platform", ["YouTube", "Instagram"], key="man_plat")
                    man_url = st.text_input("Live or Scheduled URL", placeholder="https://youtube.com/shorts/... or https://instagram.com/reel/...")
                    man_notes = st.text_input("Notes", placeholder="e.g. Scheduled for Friday 6 PM via YouTube Studio")
                    if st.form_submit_button("Record Manual Publication", type="primary"):
                        if man_url.strip():
                            record_manual_publication(
                                brief_id=active_brief_id,
                                platform=man_plat,
                                live_url=man_url.strip(),
                                notes=man_notes,
                            )
                            st.success(f"Recorded {man_plat} publication!")
                            st.rerun()
                        else:
                            st.error("Please provide a valid URL.")

        st.divider()

        # --- Section 6: Live Platform Status & Verification ---
        st.markdown("### 5. Live Platform Status & Verification")
        p_stat = pub_rec.get("platforms_status", {})
        yt_p = p_stat.get("youtube", {})
        ig_p = p_stat.get("instagram", {})

        col_stat_yt, col_stat_ig = st.columns(2)
        with col_stat_yt:
            with st.container(border=True):
                st.markdown("#### 🔴 YouTube Shorts Status")
                st.write(f"**Status:** `{yt_p.get('status', 'PENDING')}`")
                if yt_p.get("url"):
                    st.markdown(f"**Live URL:** [{yt_p.get('url')}]({yt_p.get('url')})")
                    st.caption(f"Video ID: `{yt_p.get('video_id')}`")
                if yt_p.get("scheduled_time"):
                    st.caption(f"📅 Scheduled Time: `{yt_p.get('scheduled_time')}`")
                if yt_p.get("published_at"):
                    st.caption(f"Published At: `{yt_p.get('published_at')[:19].replace('T', ' ')}`")

        with col_stat_ig:
            with st.container(border=True):
                st.markdown("#### 📸 Instagram Reels Status")
                st.write(f"**Status:** `{ig_p.get('status', 'PENDING')}`")
                if ig_p.get("permalink"):
                    st.markdown(f"**Live URL:** [{ig_p.get('permalink')}]({ig_p.get('permalink')})")
                    st.caption(f"Media ID: `{ig_p.get('media_id')}`")
                if ig_p.get("scheduled_time"):
                    st.caption(f"📅 Scheduled Time: `{ig_p.get('scheduled_time')}`")
                if ig_p.get("published_at"):
                    st.caption(f"Published At: `{ig_p.get('published_at')[:19].replace('T', ' ')}`")


# --------------------------------------------------
# TAB 7: MASTER MODEL LIBRARY (Preserved)
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
        c1, c2, c3, c4, c5, c6 = st.columns(6)
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
        with c6:
            pub_rec = load_publishing_record(active_brief_id)
            pub_val = pub_rec.get("status", "DRAFT") if pub_rec else "PENDING"
            st.metric("6. Publishing", pub_val, delta="Live" if pub_val in ("SCHEDULED", "PUBLISHED") else "Gate Lock")

        st.divider()

        if prereqs["stage_6_ready"]:
            st.success("✨ ALL PREREQUISITES MET. Brief is certified and ready for Stage 6: Video Editing & Publishing.")
        else:
            st.warning("⚠️ Pending approvals required before video editing assembly and publishing.")

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
st.caption("Wear & Wonder · Multi-Stage Fashion Content Automation · Stages 1–6 (Publishing & Scheduling) · Approval Required")
