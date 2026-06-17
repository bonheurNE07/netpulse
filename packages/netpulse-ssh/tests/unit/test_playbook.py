import pytest
import yaml
from netpulse.ssh.models import Playbook, Inventory, SshHostConfig

def test_inventory_parsing():
    yaml_data = """
    groups:
      web_servers:
        hosts:
          - ip: 192.168.1.10
            username: admin
            password: secretpassword
          - ip: 192.168.1.11
            username: admin
            ssh_key: /path/to/key
            port: 2222
    """
    data = yaml.safe_load(yaml_data)
    inventory = Inventory(**data)
    
    assert "web_servers" in inventory.groups
    group = inventory.groups["web_servers"]
    assert len(group.hosts) == 2
    
    host1 = group.hosts[0]
    assert host1.ip == "192.168.1.10"
    assert host1.username == "admin"
    assert host1.password == "secretpassword"
    
    host2 = group.hosts[1]
    assert host2.ip == "192.168.1.11"
    assert host2.ssh_key == "/path/to/key"
    assert host2.port == 2222

def test_playbook_parsing():
    yaml_data = r"""
    name: Setup Web Servers
    tasks:
      - name: Update apt
        command: apt-get update
        timeout: 60
      - name: Upgrade apt
        command: apt-get upgrade
        expect:
          - prompt: "Do you want to continue.*"
            send: "Y\n"
    """
    data = yaml.safe_load(yaml_data)
    playbook = Playbook(**data)
    
    assert playbook.name == "Setup Web Servers"
    assert len(playbook.tasks) == 2
    
    task1 = playbook.tasks[0]
    assert task1.name == "Update apt"
    assert task1.command == "apt-get update"
    assert task1.timeout == 60
    assert task1.expect is None
    
    task2 = playbook.tasks[1]
    assert task2.name == "Upgrade apt"
    assert task2.command == "apt-get upgrade"
    assert len(task2.expect) == 1
    assert task2.expect[0].prompt == "Do you want to continue.*"
    assert task2.expect[0].send == "Y\n"
