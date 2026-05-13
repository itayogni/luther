from luther.whatsapp import WhatsAppAdapter, WhatsAppMessage


def test_parse_incoming_message():
    raw = {
        "sender": "972501234567@s.whatsapp.net",
        "body": "שלום",
        "message_type": "text",
        "timestamp": 1715600000,
        "group_jid": None,
    }
    msg = WhatsAppMessage(**raw)
    assert msg.sender == "972501234567@s.whatsapp.net"
    assert msg.body == "שלום"
    assert msg.is_group is False


def test_parse_group_message():
    raw = {
        "sender": "972501234567@s.whatsapp.net",
        "body": "הודעה בקבוצה",
        "message_type": "text",
        "timestamp": 1715600000,
        "group_jid": "972501234567-1234567890@g.us",
    }
    msg = WhatsAppMessage(**raw)
    assert msg.is_group is True
    assert msg.group_jid == "972501234567-1234567890@g.us"
