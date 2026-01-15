"""Input utilities for consistent user input handling."""

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


class InputHelper:
    """Helper class for consistent input handling across the CLI."""

    @staticmethod
    def get_input_with_backspace(
        prompt: str, default: str = "", allow_empty: bool = False
    ) -> str | None:
        """Get user input with backspace support and empty input handling.

        Args:
            prompt: Prompt text to display.
            default: Default value if user enters nothing.
            allow_empty: If True, empty input returns None (for going back).

        Returns:
            User input string, default value, or None if allow_empty and input is empty.

        """
        try:
            # Use Rich to style the prompt, but use standard input() for backspace support
            styled_prompt = f"[cyan]{prompt}[/cyan]"
            console.print(styled_prompt, end=" ")
            user_input = input().strip()

            if not user_input:
                if allow_empty:
                    return None
                return default if default else ""

            return user_input
        except (EOFError, KeyboardInterrupt):
            return None

    @staticmethod
    def ask_yes_no(
        prompt: str, default: bool = True, allow_back: bool = False
    ) -> bool | None:
        """Ask a yes/no question with consistent handling.

        Args:
            prompt: Question to ask.
            default: Default value (True/False).
            allow_back: If True, allows 'b' or 'back' to return None.

        Returns:
            True/False for yes/no, or None if allow_back and user chooses back.

        """
        try:
            value = Prompt.ask(
                prompt,
                choices=["yes", "no", "y", "n", "b", "back"] if allow_back else ["yes", "no", "y", "n"],
                default="yes" if default else "no",
            )

            if allow_back and value.lower() in ["b", "back"]:
                return None

            return value.lower() in ["yes", "y"]
        except (EOFError, KeyboardInterrupt):
            return None

    @staticmethod
    def ask_choice(
        prompt: str,
        choices: list[str],
        default: str | None = None,
        allow_back: bool = False,
    ) -> str | None:
        """Ask user to select from a list of choices.

        Args:
            prompt: Question to ask.
            choices: List of valid choices.
            default: Default choice if user enters nothing.
            allow_back: If True, allows 'b' or 'back' to return None.

        Returns:
            Selected choice string, or None if allow_back and user chooses back.

        """
        try:
            valid_choices = choices.copy()
            if allow_back:
                valid_choices.extend(["b", "back"])

            value = Prompt.ask(prompt, choices=valid_choices, default=default or "")

            if allow_back and value.lower() in ["b", "back"]:
                return None

            return value
        except (EOFError, KeyboardInterrupt):
            return None

    @staticmethod
    def ask_number(
        prompt: str,
        min_value: int | None = None,
        max_value: int | None = None,
        default: int | None = None,
        allow_back: bool = False,
    ) -> int | None:
        """Ask for a number input with validation.

        Args:
            prompt: Question to ask.
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
            default: Default value if user enters nothing.
            allow_back: If True, allows 'b' or 'back' to return None.

        Returns:
            Integer value, or None if allow_back and user chooses back or invalid input.

        """
        while True:
            try:
                value = InputHelper.get_input_with_backspace(
                    prompt, default=str(default) if default else "", allow_empty=allow_back
                )

                if value is None:
                    return None

                if allow_back and value.lower() in ["b", "back"]:
                    return None

                num_value = int(value)

                if min_value is not None and num_value < min_value:
                    console.print(f"[red]Value must be at least {min_value}.[/red]\n")
                    continue

                if max_value is not None and num_value > max_value:
                    console.print(f"[red]Value must be at most {max_value}.[/red]\n")
                    continue

                return num_value
            except ValueError:
                console.print("[red]Invalid number. Please enter a valid integer.[/red]\n")
                continue
            except (EOFError, KeyboardInterrupt):
                return None

    @staticmethod
    def wait_for_continue(message: str = "\nPress Enter to continue") -> None:
        """Wait for user to press Enter before continuing.

        Args:
            message: Message to display (default: "Press Enter to continue").

        """
        Prompt.ask(message, default="")

    @staticmethod
    def confirm(prompt: str, default: bool = True) -> bool:
        """Ask for confirmation.

        Args:
            prompt: Question to ask.
            default: Default value.

        Returns:
            True if confirmed, False otherwise.

        """
        try:
            return Confirm.ask(prompt, default=default)
        except (EOFError, KeyboardInterrupt):
            return False
