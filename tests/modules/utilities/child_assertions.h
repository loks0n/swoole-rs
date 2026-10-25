// Observe GoogleTest failures across the original helper's unconditional exit(0).
#include <fcntl.h>
#include <unistd.h>
#include <cstdlib>

static int m14_journal = -1;
static pid_t m14_parent;

static void m14_child_exit() {
    if (m14_journal >= 0 && getpid() != m14_parent) {
        if (write(m14_journal, "child-exit\n", 11) != 11) _exit(125);
    }
}

class M14ChildAssertions : public ::testing::EmptyTestEventListener {
    void OnTestPartResult(const ::testing::TestPartResult &result) override {
        if (result.failed() && write(m14_journal, "failure\n", 8) != 8) _exit(125);
    }
};

static bool m14_observer_begin(const char *directory, size_t length) {
    std::string path = std::string(directory, length) + "/child-assertions.txt";
    m14_journal = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_APPEND, 0600);
    if (m14_journal < 0) return false;
    m14_parent = getpid();
    if (std::atexit(m14_child_exit) != 0) return false;
    ::testing::UnitTest::GetInstance()->listeners().Append(new M14ChildAssertions);
    return true;
}

static void m14_observer_end() {
    close(m14_journal);
    m14_journal = -1;
}
