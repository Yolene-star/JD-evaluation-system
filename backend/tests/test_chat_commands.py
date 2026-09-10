from backend.app.services.commands import parse_command


def test_parse_remove_jd_command() -> None:
    command = parse_command("请移除《前端JD》")
    assert command.action == "REMOVE_JD"
    assert command.target == "前端JD"


def test_unrecognized_message_is_chat() -> None:
    command = parse_command("请解释当前模型")
    assert command.action == "CHAT"
