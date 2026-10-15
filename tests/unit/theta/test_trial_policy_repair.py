"""TE-09R2 scope/ancestry tests. OS-level genuine-path proof is standalone.

These tests run inside the existing production-denying test harness; they never
inspect/change the real Sponsor directories or try to nest sandbox-exec.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import theta_trial


def test_review_ancestor_read_exceptions_are_exact_nodes_only():
    inbox=theta_trial.SPONSOR/'CHATGPT ANSWERS'
    outbox=theta_trial.SPONSOR/'KRONOS QUESTIONS'
    policy=theta_trial.policy(Path('/private/tmp/runtime'),inbox,outbox,8970,Path('/private/tmp/probe'))
    expected='(allow file-read-metadata file-read-data (literal "'+str(theta_trial.SPONSOR.parent)+'")\n(literal "'+str(theta_trial.SPONSOR)+'"))'
    assert expected in policy
    assert '(allow file-read-metadata file-read-data (subpath' not in policy
    assert '(deny file* (require-all (subpath' in policy
    assert '(require-not (subpath "'+str(inbox)+'"))' in policy
    assert '(require-not (subpath "'+str(outbox)+'"))' in policy
    assert '(deny file-write* (require-all' in policy


def test_disposable_paths_do_not_emit_an_unfiltered_read_allow():
    policy=theta_trial.policy(Path('/private/tmp/runtime'),Path('/private/tmp/answers'),
                              Path('/private/tmp/questions'),8971,Path('/private/tmp/probe'))
    assert '(allow file-read-metadata file-read-data' not in policy


@pytest.mark.parametrize('component',['KRONOS REVIEW PACK','Theta Earners',
                                    'KRONOS QUESTIONS','CHATGPT ANSWERS'])
def test_same_named_symlink_ancestry_is_rejected(tmp_path,component,monkeypatch):
    review=tmp_path/'KRONOS REVIEW PACK';sponsor=review/'Theta Earners'
    inbox=sponsor/'CHATGPT ANSWERS';outbox=sponsor/'KRONOS QUESTIONS'
    inbox.mkdir(mode=0o700,parents=True);outbox.mkdir(mode=0o700)
    selected={'KRONOS REVIEW PACK':review,'Theta Earners':sponsor,
              'KRONOS QUESTIONS':outbox,'CHATGPT ANSWERS':inbox}[component]
    moved=tmp_path/'moved';selected.rename(moved);selected.symlink_to(moved,target_is_directory=True)
    root=tmp_path/'runtime'
    monkeypatch.setattr(theta_trial,'SPONSOR',sponsor)
    monkeypatch.setattr(theta_trial,'GENUINE_ROOT',root)
    args=SimpleNamespace(mode='GENUINE_TRIAL',root=root,inbox=inbox,outbox=outbox,port=8970,child=True)
    with pytest.raises(ValueError,match='PATH_INVALID'):theta_trial.preflight(args)
    assert not root.exists()


@pytest.mark.parametrize('change',['traversal','foreign_inbox','foreign_outbox'])
def test_genuine_paths_stay_exact_and_normalized(tmp_path,change,monkeypatch):
    sponsor=tmp_path/'KRONOS REVIEW PACK/Theta Earners'
    inbox=sponsor/'CHATGPT ANSWERS';outbox=sponsor/'KRONOS QUESTIONS'
    inbox.mkdir(mode=0o700,parents=True);outbox.mkdir(mode=0o700)
    root=tmp_path/'runtime'
    monkeypatch.setattr(theta_trial,'SPONSOR',sponsor)
    monkeypatch.setattr(theta_trial,'GENUINE_ROOT',root)
    args=SimpleNamespace(mode='GENUINE_TRIAL',root=root,inbox=inbox,outbox=outbox,port=8970,child=True)
    if change=='traversal':args.inbox=sponsor/'foreign/../CHATGPT ANSWERS'
    elif change=='foreign_inbox':args.inbox=tmp_path/'foreign'
    else:args.outbox=tmp_path/'foreign'
    with pytest.raises(ValueError,match='PATH_INVALID'):theta_trial.preflight(args)
    assert not root.exists()
