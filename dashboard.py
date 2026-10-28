
import streamlit as st
from pathlib import Path

from app.idea_intake import create_research_brief, save_research_brief
from app.fashion_ai import interpret_idea_with_gemini
from app.model_library import (
    ALLOWED_MODELS,
    load_models,
    save_model,
    set_model_approval,
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
st.caption("Your fashion content workspace")

idea_tab, models_tab = st.tabs(["Idea Studio", "Master Models"])


# --------------------------------------------------
# IDEA STUDIO
# --------------------------------------------------
with idea_tab:
    st.subheader("Idea Studio")
    st.write(
        "Describe any fashion video idea. "
        "Review the extracted details before saving your brief."
    )

    with st.form("idea_form"):
        idea = st.text_area(
            "What fashion video do you want to create?",
            placeholder=(
                "Example: Create six jeans and top combinations "
                "for college girls using my female master model."
            ),
            height=120,
        )

        reference_url = st.text_input(
            "Reference video URL (optional)"
        )

        additional_requirements = st.text_area(
            "Additional requirements (optional)"
        )

        submitted = st.form_submit_button(
            "Review my idea",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not idea.strip():
            st.error("Please enter a fashion video idea.")
        else:
            try:
                clean_requirements = additional_requirements.strip() or None
                clean_reference = reference_url.strip() or None
                with st.spinner("Gemini is interpreting your idea. This may take up to a minute..."):
                    ai_result = interpret_idea_with_gemini(
                        idea=idea,
                        additional_requirements=clean_requirements,
                        reference_url=clean_reference,
                    )

                # Keep the existing brief schema and let the user review/edit AI suggestions.
                brief = create_research_brief(
                    idea=idea,
                    requested_characters=ai_result["requested_characters"],
                    audience=ai_result["audience"],
                    outfit_count=ai_result["outfit_count"],
                    additional_requirements=clean_requirements,
                )
                brief["reference_url"] = clean_reference
                brief["ai_analysis"] = ai_result
                brief["interpretation_method"] = "GEMINI_API"
                brief["interpretation_note"] = (
                    "Gemini interpreted this idea. This is planning only: "
                    "live research and outfit verification have not occurred."
                )
                st.session_state["pending_brief"] = brief

            except (ValueError, TypeError, RuntimeError, OSError) as exc:
                st.error(f"Could not prepare the AI brief: {exc}")

    # Review the draft before saving.
    if "pending_brief" in st.session_state:
        brief = st.session_state["pending_brief"]

        st.divider()
        st.subheader("Review your idea")
        st.info(
            "Gemini has interpreted the idea. This is planning only: live web research, "
            "source verification, outfit approval, and image generation have not started."
        )

        ai_analysis = brief.get("ai_analysis", {})
        if ai_analysis:
            with st.expander("Gemini's interpretation and styling plan", expanded=True):
                if ai_analysis.get("concept_summary"):
                    st.markdown("**Concept summary**")
                    st.write(ai_analysis["concept_summary"])
                if ai_analysis.get("styling_direction"):
                    st.markdown("**Professional styling direction**")
                    st.write(ai_analysis["styling_direction"])
                if ai_analysis.get("research_plan"):
                    st.markdown("**Research tasks (not yet performed)**")
                    for task in ai_analysis["research_plan"]:
                        st.markdown(f"- {task}")
                if ai_analysis.get("validation_checklist"):
                    st.markdown("**Outfit validation checklist**")
                    for check in ai_analysis["validation_checklist"]:
                        st.markdown(f"- {check}")
                if ai_analysis.get("assumptions"):
                    st.markdown("**Assumptions to review**")
                    for item in ai_analysis["assumptions"]:
                        st.markdown(f"- {item}")
                if ai_analysis.get("clarifying_questions"):
                    st.markdown("**Questions Gemini thinks may need clarification**")
                    for question in ai_analysis["clarifying_questions"]:
                        st.markdown(f"- {question}")
                st.caption("These are AI suggestions, not verified fashion research.")

        st.write("**Original idea**")
        st.write(brief["idea_original"])

        audience_options = [
            "Not specified",
            "College girls",
            "College boys",
            "Couples",
            "General audience",
        ]

        current_audience = brief.get("audience")
        audience_index = (
            audience_options.index(current_audience)
            if current_audience in audience_options
            else 0
        )

        selected_audience = st.selectbox(
            "Target audience",
            audience_options,
            index=audience_index,
            key="review_audience",
        )

        current_count = brief.get("outfit_count")
        outfit_count = st.number_input(
            "Number of outfits",
            min_value=1,
            max_value=20,
            value=int(current_count) if current_count else 6,
            step=1,
            key="review_outfit_count",
        )

        character_labels = {
            "WW-CHAR-01": "Female Model 01",
            "WW-CHAR-02": "Female Model 02",
            "WW-CHAR-03": "Male Model 01",
        }

        selected_characters = st.multiselect(
            "Requested models",
            options=list(character_labels),
            default=brief.get("requested_characters", []),
            format_func=lambda item: character_labels[item],
            key="review_characters",
        )

        st.write(
            "**Reference URL:**",
            brief.get("reference_url") or "None",
        )
        st.write(
            "**Additional requirements:**",
            brief.get("additional_requirements") or "None",
        )
        st.caption(f"Brief ID: {brief['brief_id']}")

        save_col, discard_col = st.columns(2)

        with save_col:
            if st.button(
                "Confirm details and save",
                type="primary",
                use_container_width=True,
                key="confirm_save_brief",
            ):
                try:
                    updated = create_research_brief(
                        idea=brief["idea_original"],
                        requested_characters=selected_characters,
                        audience=(
                            None
                            if selected_audience == "Not specified"
                            else selected_audience
                        ),
                        outfit_count=int(outfit_count),
                        additional_requirements=brief.get(
                            "additional_requirements"
                        ),
                    )

                    # Keep the original draft ID.
                    updated["brief_id"] = brief["brief_id"]
                    updated["reference_url"] = brief.get("reference_url")
                    updated["ai_analysis"] = brief.get("ai_analysis", {})
                    updated["interpretation_method"] = brief.get(
                        "interpretation_method", updated.get("interpretation_method")
                    )
                    updated["interpretation_note"] = brief.get(
                        "interpretation_note", updated.get("interpretation_note")
                    )

                    save_research_brief(updated)

                    st.session_state.pop("pending_brief", None)
                    st.session_state["saved_message"] = (
                        f"Brief {updated['brief_id']} saved. "
                        "Research and outfit approval remain pending."
                    )
                    st.rerun()

                except (ValueError, TypeError, OSError) as exc:
                    st.error(f"Could not save the brief: {exc}")

        with discard_col:
            if st.button(
                "Discard draft",
                use_container_width=True,
                key="discard_brief",
            ):
                st.session_state.pop("pending_brief", None)
                st.rerun()

    if "saved_message" in st.session_state:
        st.success(st.session_state.pop("saved_message"))


# --------------------------------------------------
# MASTER MODEL LIBRARY
# --------------------------------------------------
with models_tab:
    st.subheader("Master Model Library")
    st.write(
        "Register your reference images and identity rules. "
        "New or updated model profiles require your approval."
    )

    # Show messages after a rerun.
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
        st.info(
            "No models registered yet. "
            "Upload your first reference image below."
        )

    for profile in profiles:
        model_id = profile.get("model_id")

        if model_id not in ALLOWED_MODELS:
            continue

        with st.container(border=True):
            st.markdown(
                f"**{profile.get('display_name', 'Unnamed model')}**"
            )
            st.caption(model_id)

            status = profile.get(
                "approval_status", "PENDING_APPROVAL"
            )
            st.write("**Approval status:**", status)

            st.write(
                "**Fixed identity characteristics:**",
                profile.get("identity_notes") or "Not provided",
            )
            st.write(
                "**Hair styling rules:**",
                profile.get("hair_rules") or "Not provided",
            )

            # Display the stored reference image.
            relative_path = profile.get("reference_image", "")
            image_path = (PROJECT_DIR / relative_path).resolve()

            # Prevent a malformed JSON path from accessing files outside
            # the project directory.
            try:
                image_path.relative_to(PROJECT_DIR.resolve())
                path_is_inside_project = True
            except ValueError:
                path_is_inside_project = False

            if (
                path_is_inside_project
                and image_path.is_file()
                and image_path.suffix.lower()
                in {".png", ".jpg", ".jpeg", ".webp"}
            ):
                st.image(
                    str(image_path),
                    caption=profile.get(
                        "display_name", "Master reference"
                    ),
                    use_container_width=True,
                )
            else:
                st.warning(
                    "The reference image could not be found. "
                    "Upload it again using the form below."
                )

            approve_col, pending_col = st.columns(2)

            with approve_col:
                if status == "APPROVED":
                    st.button(
                        "Already approved",
                        key=f"approved_disabled_{model_id}",
                        disabled=True,
                        use_container_width=True,
                    )
                elif st.button(
                    "Approve model",
                    key=f"approve_{model_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        updated = set_model_approval(model_id, True)
                        st.session_state["model_action_message"] = (
                            f"{updated['display_name']} is now APPROVED."
                        )
                        st.rerun()
                    except (ValueError, OSError) as exc:
                        st.error(f"Could not approve model: {exc}")

            with pending_col:
                if status == "PENDING_APPROVAL":
                    st.button(
                        "Already pending",
                        key=f"pending_disabled_{model_id}",
                        disabled=True,
                        use_container_width=True,
                    )
                elif st.button(
                    "Return to pending",
                    key=f"pending_{model_id}",
                    use_container_width=True,
                ):
                    try:
                        updated = set_model_approval(model_id, False)
                        st.session_state["model_action_message"] = (
                            f"{updated['display_name']} is now pending approval."
                        )
                        st.rerun()
                    except (ValueError, OSError) as exc:
                        st.error(f"Could not update model: {exc}")

    # --------------------------------------------------
    # ADD OR UPDATE MODEL
    # --------------------------------------------------
    st.divider()
    st.markdown("### Add or update a model")

    with st.form("model_form"):
        selected_model_id = st.selectbox(
            "Model ID",
            list(ALLOWED_MODELS.keys()),
            format_func=lambda item: (
                f"{item} — {model_labels[item]}"
            ),
        )

        existing = profile_by_id.get(selected_model_id, {})

        display_name = st.text_input(
            "Display name",
            value=existing.get(
                "display_name", model_labels[selected_model_id]
            ),
        )

        identity_notes = st.text_area(
            "Fixed identity characteristics",
            value=existing.get("identity_notes", ""),
            placeholder=(
                "Describe face, hairline, natural hair color, "
                "natural texture and body proportions."
            ),
        )

        hair_rules = st.text_area(
            "Hair styling rules",
            value=existing.get("hair_rules", ""),
            placeholder=(
                "Describe fixed hair identity and approved styling "
                "variations for casual and formal outfits."
            ),
        )

        uploaded_image = st.file_uploader(
            "Upload full-body master reference",
            type=["png", "jpg", "jpeg", "webp"],
            key="master_model_upload",
        )

        st.caption(
            "Replacing a model image resets its approval status to pending."
        )

        save_model_button = st.form_submit_button(
            "Save model profile",
            type="primary",
            use_container_width=True,
        )

    if save_model_button:
        if not display_name.strip():
            st.error("Please enter a display name.")
        elif uploaded_image is None:
            st.error(
                "Please upload the full-body reference image. "
                "This is required for both new and updated profiles."
            )
        else:
            try:
                profile = save_model(
                    model_id=selected_model_id,
                    display_name=display_name,
                    identity_notes=identity_notes,
                    hair_rules=hair_rules,
                    image_bytes=uploaded_image.getvalue(),
                    image_extension=(
                        "."
                        + uploaded_image.name.rsplit(".", 1)[-1].lower()
                    ),
                )

                st.session_state["model_action_message"] = (
                    f"{profile['display_name']} saved. "
                    "Status: PENDING_APPROVAL."
                )
                st.rerun()

            except (ValueError, TypeError, OSError) as exc:
                st.error(f"Could not save model: {exc}")


# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.divider()
st.caption("Wear & Wonder · Local prototype · Approval required")
