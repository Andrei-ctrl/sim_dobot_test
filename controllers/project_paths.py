"""Resolve Webots project root (repo root containing data/)."""

import os


def project_root_from_controller_file(controller_file):
    """Given .../controllers/<pkg>/<controller>.py return .../sim_dobot_test."""
    controllers_dir = os.path.dirname(os.path.dirname(os.path.abspath(controller_file)))
    return os.path.dirname(controllers_dir)
