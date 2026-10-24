"""A capture typed in place: Compass titles it and fixes the typing, never more."""
from backend import capture_writer
from backend.accounts import Accounts
from test_accounts import accounts, api, hub_text, vault  # noqa: F401 -- fixtures
from backend.opportunities import _today

TYPED = "Met the CIO in teh lift\n- MACC befor ADIPEC\n- see [[Alpha Data]]"


class Llm:
    def __init__(self, answer=None, error=None, available=True):
        self.answer, self.error, self._available = answer, error, available
        self.asked = []

    def available(self):
        return self._available

    def complete(self, messages, timeout=120.0):
        self.asked.append(messages)
        if self.error:
            raise self.error
        return self.answer


class Api:
    def __init__(self, llm):
        self.llm = llm


def test_compass_titles_the_capture_and_fixes_its_typing():
    answer = "TITLE: Lift chat with the CIO\n\nMet the CIO in the lift\n- MACC before ADIPEC\n- see [[Alpha Data]]"
    result = capture_writer.compose(Api(Llm(answer)), TYPED)
    assert result == {"title": "Lift chat with the CIO", "tidied": True, "note": "",
                      "text": "Met the CIO in the lift\n- MACC before ADIPEC\n- see [[Alpha Data]]"}


def test_a_fenced_answer_is_unwrapped_and_a_long_title_is_cut():
    answer = "```\nTITLE: \"One two three four five six seven eight nine ten\"\n\n" + TYPED.replace("teh", "the") + "\n```"
    result = capture_writer.compose(Api(Llm(answer)), TYPED)
    assert result["title"] == "One two three four five six seven eight"
    assert result["tidied"]


def test_a_renamed_link_keeps_the_title_but_not_the_text():
    answer = "TITLE: Lift chat\n\n" + TYPED.replace("[[Alpha Data]]", "[[alpha data]]")
    result = capture_writer.compose(Api(Llm(answer)), TYPED)
    assert result["title"] == "Lift chat" and result["text"] == TYPED and not result["tidied"]


def test_a_rewrite_is_refused():
    answer = "TITLE: Lift chat\n\nThe CIO and I had a long and productive conversation about many things\nin the lift\ntoday"
    assert capture_writer.compose(Api(Llm(answer)), TYPED)["text"] == TYPED


def test_no_compass_or_a_failing_one_saves_as_typed():
    for llm in (None, Llm(available=False), Llm(error=RuntimeError("down")), Llm("no title line here")):
        result = capture_writer.compose(Api(llm), TYPED)
        assert result["title"] == "Capture" and result["text"] == TYPED and not result["tidied"]
        assert result["note"]


def test_a_capture_without_a_title_is_titled_and_tidied_on_save(api, vault):  # noqa: F811
    api.llm = Llm("TITLE: Lift chat\n\nMet the CIO in the lift\n- MACC before ADIPEC\n- see [[Alpha Data]]")
    added = Accounts(api).add_capture("customer", "Contoso", "", TYPED, "Mahmoud")
    assert added["added"] == {"title": "Lift chat", "tidied": True, "note": ""}
    text = hub_text(vault, "Customers", "Contoso", "Contoso-captures.md")
    assert f"## {_today()} — Lift chat\n\n*Added by Mahmoud on " in text
    assert "Met the CIO in the lift\n- MACC before ADIPEC" in text


def test_a_capture_with_a_title_is_saved_as_typed(api, vault):  # noqa: F811
    api.llm = Llm("TITLE: Something else\n\nchanged")
    added = Accounts(api).add_capture("customer", "Contoso", "My title", TYPED, "Mahmoud")
    assert added["added"]["title"] == "My title" and not api.llm.asked
    assert "Met the CIO in teh lift" in hub_text(vault, "Customers", "Contoso", "Contoso-captures.md")
