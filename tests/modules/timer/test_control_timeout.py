"""Timer differential classification without starting PHP or child processes."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


class Engine:
    def __init__(self, name):
        self.name = name

    def metadata(self):
        return {"name": self.name}

    def command(self, *arguments):
        return [self.name, *map(str, arguments)]


class ControlTimeoutTests(unittest.TestCase):
    def exercise(self, filename, flags, mode):
        path = Path(__file__).with_name(filename)
        spec = importlib.util.spec_from_file_location("timer_test_driver", path)
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        per_engine = 16 if filename == "bailout.py" else 12
        report = None
        calls = 0

        def save(_path, value):
            nonlocal report
            report = value

        def run(command, **_kwargs):
            nonlocal calls
            index = calls % per_engine
            calls += 1
            engine = command[0]
            if mode == "timeout" and engine == "original" and index == 0:
                raise subprocess.TimeoutExpired(command, 5, output="first control output")
            oom = "oom" in command
            if filename == "bailout.py":
                stdout = "CALL\nSHUTDOWN 1\nSTATE timer\n"
            else:
                stdout = ("" if flags else "CALL\n") + "DTOR\nSHUTDOWN\n"
            stderr = "Allowed memory size" if oom else ""
            if mode == "mismatch" and engine == "candidate" and index == 0:
                stderr += "candidate diagnostic"
            return subprocess.CompletedProcess(command, 255 if oom else 0, stdout, stderr)

        argv = [str(path), "--engine", "original=/unused/original", "--engine",
                "candidate=/unused/candidate", "--engine", "third=/unused/third", *flags]
        with patch.object(sys, "argv", argv), \
             patch.object(driver, "parse_engines", return_value=[Engine(n) for n in ("original", "candidate", "third")]), \
             patch.object(driver, "run_isolated", side_effect=run), \
             patch.object(driver, "write_report", side_effect=save), \
             contextlib.redirect_stdout(io.StringIO()):
            code = driver.main()
        self.assertEqual(calls, 3 * per_engine)
        self.assertEqual(len(report["results"]), 3 * per_engine)
        self.assertEqual(code, int(mode != "success"))
        self.assertEqual(report["passed"], mode == "success")
        first, second, third = [report["results"][n * per_engine] for n in range(3)]
        if mode == "timeout":
            self.assertIn("first control output", first["stdout"])
            self.assertFalse(first["passed"])
            for row in (second, third):
                self.assertTrue(row["valid"])
                self.assertFalse(row["matches_first_engine"])
                self.assertFalse(row["control_available"])
                self.assertFalse(row["passed"])
            for row in report["results"][per_engine + 1:2 * per_engine]:
                self.assertTrue(row["control_available"])
                self.assertTrue(row["passed"])
        elif mode == "mismatch":
            self.assertTrue(second["control_available"])
            self.assertTrue(second["valid"])
            self.assertFalse(second["matches_first_engine"])
            self.assertFalse(second["passed"])
            self.assertTrue(third["passed"])
        else:
            self.assertTrue(all(row["control_available"] and row["passed"] for row in report["results"]))

    def test_original_timeout_cannot_promote_any_candidate_to_control(self):
        self.profiles("timeout")

    def test_available_original_still_detects_different_candidate(self):
        self.profiles("mismatch")

    def test_matching_terminal_outcomes_still_pass(self):
        self.profiles("success")

    def profiles(self, mode):
        for filename, flags in [("bailout.py", []), ("destructor_bailout.py", []),
                                ("destructor_bailout.py", ["--idle-clear"]),
                                ("destructor_bailout.py", ["--event-exit"])]:
            with self.subTest(driver=filename, flags=flags, mode=mode):
                self.exercise(filename, flags, mode)


if __name__ == "__main__":
    unittest.main()
