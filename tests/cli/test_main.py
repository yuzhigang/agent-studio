from unittest.mock import patch, MagicMock
import pytest
from src.cli.main import main


def test_list_instances_no_args():
    with pytest.raises(SystemExit):
        main(["list-instances"])
