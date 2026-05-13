from luther.models import Memory, ApprovedGroup


def test_create_memory(db):
    mem = Memory(
        memory_type="project",
        key="q4_dashboard",
        value="Dashboard project is in progress",
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    assert mem.id is not None
    assert mem.memory_type == "project"
    assert mem.key == "q4_dashboard"


def test_create_approved_group(db):
    group = ApprovedGroup(
        group_jid="972501234567-1234567890@g.us",
        display_name="Q4 Digital Team",
        active=True,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    assert group.id is not None
    assert group.active is True


def test_memory_types(db):
    for mtype in ["static", "project", "preference", "conversation"]:
        mem = Memory(memory_type=mtype, key=f"test_{mtype}", value="test")
        db.add(mem)
    db.commit()
    assert db.query(Memory).count() == 4
