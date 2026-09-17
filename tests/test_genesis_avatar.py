"""Tests for Genesis Avatar Interface."""

import unittest
from genesis_avatar import (
    AvatarUIMode,
    AvatarState,
    AvatarCapabilities,
    AvatarConfig,
    AvatarBinding,
    MockAvatarInterface,
    create_avatar_binding,
)


class TestAvatarUIMode(unittest.TestCase):
    """Test AvatarUIMode enum."""
    
    def test_modes_exist(self):
        self.assertEqual(AvatarUIMode.HIDDEN.value, "hidden")
        self.assertEqual(AvatarUIMode.SMALL.value, "small")
        self.assertEqual(AvatarUIMode.STANDARD.value, "standard")
        self.assertEqual(AvatarUIMode.FULL_SCREEN.value, "full_screen")
    
    def test_mode_count(self):
        self.assertEqual(len(list(AvatarUIMode)), 4)


class TestAvatarState(unittest.TestCase):
    """Test AvatarState enum."""
    
    def test_states_exist(self):
        self.assertEqual(AvatarState.IDLE.value, "idle")
        self.assertEqual(AvatarState.THINKING.value, "thinking")
        self.assertEqual(AvatarState.EXECUTING.value, "executing")
        self.assertEqual(AvatarState.AWAITING_INPUT.value, "awaiting_input")
        self.assertEqual(AvatarState.ERROR.value, "error")
        self.assertEqual(AvatarState.DISABLED.value, "disabled")


class TestAvatarCapabilities(unittest.TestCase):
    """Test AvatarCapabilities dataclass."""
    
    def test_default_capabilities(self):
        caps = AvatarCapabilities()
        self.assertTrue(caps.can_propose_plans)
        self.assertTrue(caps.can_execute_actions)
        self.assertFalse(caps.can_accept_voice)
    
    def test_custom_capabilities(self):
        caps = AvatarCapabilities(can_accept_voice=True, custom={"test": "value"})
        self.assertTrue(caps.can_accept_voice)
        self.assertEqual(caps.custom["test"], "value")


class TestAvatarConfig(unittest.TestCase):
    """Test AvatarConfig dataclass."""
    
    def test_default_config(self):
        config = AvatarConfig()
        self.assertEqual(config.mode, AvatarUIMode.STANDARD)
        self.assertEqual(config.position, "right")
        self.assertEqual(config.width, 400)
        self.assertEqual(config.height, 600)
        self.assertEqual(config.opacity, 1.0)
        self.assertEqual(config.theme, "system")
        self.assertFalse(config.auto_hide)
        self.assertTrue(config.show_state_indicator)
        self.assertTrue(config.show_capability_badges)
        self.assertEqual(config.hotkey_toggle, "ctrl+shift+g")
        self.assertEqual(config.hotkey_cycle_mode, "ctrl+shift+alt+g")
    
    def test_custom_config(self):
        config = AvatarConfig(
            mode=AvatarUIMode.FULL_SCREEN,
            position="center",
            width=800,
            height=600,
            theme="dark"
        )
        self.assertEqual(config.mode, AvatarUIMode.FULL_SCREEN)
        self.assertEqual(config.position, "center")
        self.assertEqual(config.width, 800)
        self.assertEqual(config.theme, "dark")


class TestMockAvatarInterface(unittest.TestCase):
    """Test MockAvatarInterface implementation."""
    
    def setUp(self):
        self.interface = MockAvatarInterface()
    
    def test_initial_state(self):
        self.assertEqual(self.interface._mode, AvatarUIMode.HIDDEN)
        self.assertEqual(self.interface._state, AvatarState.IDLE)
    
    def test_set_mode(self):
        self.interface.set_mode(AvatarUIMode.STANDARD)
        self.assertEqual(self.interface._mode, AvatarUIMode.STANDARD)
        
        self.interface.set_mode(AvatarUIMode.FULL_SCREEN)
        self.assertEqual(self.interface._mode, AvatarUIMode.FULL_SCREEN)
    
    def test_set_state(self):
        self.interface.set_state(AvatarState.THINKING)
        self.assertEqual(self.interface._state, AvatarState.THINKING)
        
        self.interface.set_state(AvatarState.ERROR)
        self.assertEqual(self.interface._state, AvatarState.ERROR)
    
    def test_show_message(self):
        self.interface.show_message("Test message", "info")
        self.assertEqual(len(self.interface._messages), 1)
        self.assertEqual(self.interface._messages[0]["message"], "Test message")
        self.assertEqual(self.interface._messages[0]["level"], "info")
    
    def test_show_plan(self):
        plan = {"action": "test", "params": {}}
        self.interface.show_plan(plan)
        self.assertEqual(len(self.interface._plans), 1)
        self.assertEqual(self.interface._plans[0], plan)
    
    def test_show_memory(self):
        memory = {"items": ["item1", "item2"]}
        self.interface.show_memory(memory)
        self.assertEqual(self.interface._memory, memory)
    
    def test_update_capabilities(self):
        caps = AvatarCapabilities(can_accept_voice=True)
        self.interface.update_capabilities(caps)
        self.assertEqual(self.interface._capabilities.can_accept_voice, True)
    
    def test_config_operations(self):
        config = self.interface.get_config()
        self.assertIsInstance(config, AvatarConfig)
        
        new_config = AvatarConfig(mode=AvatarUIMode.SMALL)
        self.interface.set_config(new_config)
        self.assertEqual(self.interface.get_config().mode, AvatarUIMode.SMALL)


class TestAvatarBinding(unittest.TestCase):
    """Test AvatarBinding class."""
    
    def setUp(self):
        self.interface = MockAvatarInterface()
        self.config = AvatarConfig(mode=AvatarUIMode.STANDARD)
        self.binding = AvatarBinding(self.interface, self.config)
    
    def test_initial_state(self):
        self.assertEqual(self.binding.current_mode, AvatarUIMode.STANDARD)
        self.assertEqual(self.binding.current_state, AvatarState.IDLE)
    
    def test_set_mode(self):
        self.binding.set_mode(AvatarUIMode.FULL_SCREEN)
        self.assertEqual(self.binding.current_mode, AvatarUIMode.FULL_SCREEN)
        self.assertEqual(self.interface._mode, AvatarUIMode.FULL_SCREEN)
    
    def test_cycle_mode(self):
        self.assertEqual(self.binding.current_mode, AvatarUIMode.STANDARD)
        self.binding.cycle_mode()
        self.assertEqual(self.binding.current_mode, AvatarUIMode.FULL_SCREEN)
        self.binding.cycle_mode()
        self.assertEqual(self.binding.current_mode, AvatarUIMode.HIDDEN)
        self.binding.cycle_mode()
        self.assertEqual(self.binding.current_mode, AvatarUIMode.SMALL)
        self.binding.cycle_mode()
        self.assertEqual(self.binding.current_mode, AvatarUIMode.STANDARD)
    
    def test_set_state(self):
        self.binding.set_state(AvatarState.THINKING)
        self.assertEqual(self.binding.current_state, AvatarState.THINKING)
        self.assertEqual(self.interface._state, AvatarState.THINKING)
    
    def test_propose_plan(self):
        plan = {"action": "test", "description": "Test action"}
        self.binding.propose_plan(plan)
        self.assertEqual(self.binding.current_state, AvatarState.AWAITING_INPUT)
        self.assertEqual(len(self.interface._plans), 1)
    
    def test_execute_action(self):
        action = {"description": "Test action"}
        self.binding.execute_action(action)
        self.assertEqual(self.binding.current_state, AvatarState.EXECUTING)
    
    def test_complete_action_success(self):
        self.binding.complete_action({"success": True, "result": "done"})
        self.assertEqual(self.binding.current_state, AvatarState.IDLE)
    
    def test_complete_action_failure(self):
        self.binding.complete_action({"success": False, "error": "failed"})
        self.assertEqual(self.binding.current_state, AvatarState.IDLE)
    
    def test_show_error(self):
        self.binding.show_error("Test error")
        self.assertEqual(self.binding.current_state, AvatarState.ERROR)
    
    def test_think(self):
        self.binding.think("Processing...")
        self.assertEqual(self.binding.current_state, AvatarState.THINKING)
    
    def test_update_memory_display(self):
        memory = {"session": "test"}
        self.binding.update_memory_display(memory)
        self.assertEqual(self.interface._memory, memory)
    
    def test_mode_change_callback(self):
        callback_called = []
        def callback(mode):
            callback_called.append(mode)
        
        self.binding.on_mode_change(callback)
        self.binding.set_mode(AvatarUIMode.SMALL)
        self.assertEqual(len(callback_called), 1)
        self.assertEqual(callback_called[0], AvatarUIMode.SMALL)
    
    def test_state_change_callback(self):
        callback_called = []
        def callback(state):
            callback_called.append(state)
        
        self.binding.on_state_change(callback)
        self.binding.set_state(AvatarState.EXECUTING)
        self.assertEqual(len(callback_called), 1)
        self.assertEqual(callback_called[0], AvatarState.EXECUTING)
    
    def test_update_config(self):
        self.binding.update_config(width=500, height=700, theme="dark")
        config = self.binding.get_config()
        self.assertEqual(config.width, 500)
        self.assertEqual(config.height, 700)
        self.assertEqual(config.theme, "dark")


class TestCreateAvatarBinding(unittest.TestCase):
    """Test factory function."""
    
    def test_create_default(self):
        binding = create_avatar_binding()
        self.assertIsInstance(binding, AvatarBinding)
        self.assertEqual(binding.current_mode, AvatarUIMode.STANDARD)
    
    def test_create_with_mode(self):
        binding = create_avatar_binding(AvatarUIMode.FULL_SCREEN)
        self.assertEqual(binding.current_mode, AvatarUIMode.FULL_SCREEN)


if __name__ == "__main__":
    unittest.main()