"""Exercise the project's hardened workflow hook against disposable Git history."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


HOOK = Path(os.environ.get('PRE_PUSH_HOOK', Path(__file__).parents[1] / '.githooks/pre-push')).resolve()
ZERO = '0' * 40


class PrePushTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Hook Test')
        self.git('config', 'user.email', 'hook-test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.base = self.commit('v0.1 Initial version')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True, stderr=subprocess.PIPE).strip()

    def commit(self, title):
        self.git('commit', '-q', '--allow-empty', '-m', title)
        return self.git('rev-parse', 'HEAD')

    def check_push(self, local_sha, remote_sha=None, branch='main'):
        line = 'refs/heads/work {} refs/heads/{} {}\n'.format(local_sha, branch, remote_sha or self.base)
        return subprocess.run(['/bin/sh', str(HOOK)], input=line, text=True,
                              capture_output=True, cwd=self.repo)

    def test_rejects_docs_commit_to_main(self):
        result = self.check_push(self.commit('docs: update guide'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('docs: update guide', result.stderr)

    def test_allows_version_commit_to_main(self):
        self.assertEqual(self.check_push(self.commit('v0.2 Add routing guide')).returncode, 0)

    def test_allows_numeric_patch_version(self):
        self.assertEqual(self.check_push(self.commit('v0.1.1 Repair connection cleanup')).returncode, 0)

    def test_rejects_hidden_nonversion_commit_in_range(self):
        self.commit('fix: intermediate change')
        result = self.check_push(self.commit('v0.2 Release'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fix: intermediate change', result.stderr)

    def test_allows_nonversion_commit_on_temporary_branch(self):
        self.assertEqual(self.check_push(self.commit('docs: preview'), branch='ci-check-docs').returncode, 0)

    def test_checks_all_history_when_creating_main(self):
        result = self.check_push(self.commit('docs: incomplete release'), remote_sha=ZERO)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_malformed_numeric_versions(self):
        for subject in ['v0x.1oops Title', 'v0.1.a Title']:
            with self.subTest(subject=subject):
                self.git('reset', '--hard', self.base)
                self.assertNotEqual(self.check_push(self.commit(subject)).returncode, 0)

    def test_rejects_empty_topic_in_raw_commit(self):
        tree = self.git('rev-parse', 'HEAD^{tree}')
        raw = ('tree {}\nparent {}\nauthor Hook Test <hook-test@example.invalid> 0 +0000\n'
               'committer Hook Test <hook-test@example.invalid> 0 +0000\n\nv0.1 \n').format(tree, self.base)
        sha = subprocess.check_output(['git', 'hash-object', '-t', 'commit', '-w', '--stdin'],
                                      input=raw, cwd=self.repo, text=True).strip()
        self.assertNotEqual(self.check_push(sha).returncode, 0)

    def test_refuses_unreadable_remote_commit_range(self):
        result = self.check_push(self.commit('v0.2 Release'), remote_sha='1' * 40)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
