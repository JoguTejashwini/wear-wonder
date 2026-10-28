
from app.idea_intake import create_research_brief, save_research_brief


def main():
    print("=== Wear & Wonder Automation ===")

    idea = input("\nWhat should your fashion video be about?\n> ")

    brief = create_research_brief(idea)

    print("\nPlease review the extracted details:")
    for key, value in brief.items():
        print(f"{key}: {value}")

    save_choice = input(
        "\nSave this research brief locally? (y/n): "
    ).strip().lower()

    if save_choice == "y":
        save_research_brief(brief)
        print("\nResearch brief saved to data/research.json.")
    else:
        print("\nBrief was not saved.")


if __name__ == "__main__":
    main()
