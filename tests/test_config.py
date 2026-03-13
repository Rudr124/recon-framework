import os
import importlib
import unittest


class TestConfig(unittest.TestCase):
    def test_config_env_loading(self):
        # set an env var and reload core.config
        os.environ["SECURITYTRAILS_KEY"] = "env_test_key"
        # import and reload
        import core.config as config
        importlib.reload(config)
        self.assertEqual(getattr(config, "SECURITYTRAILS_KEY"), "env_test_key")
        # cleanup
        del os.environ["SECURITYTRAILS_KEY"]
