#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static const char *workspace_url = "http://127.0.0.1:8947/swing/opportunities";
static const char *control_schema = "KRONOS_BROWSER_BACKEND_CONTROL_V1";

static int connect_backend(void) {
    int socket_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (socket_fd < 0) return -1;

    struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
    (void)setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(8947);
    if (
        inet_pton(AF_INET, "127.0.0.1", &address.sin_addr) != 1 ||
        connect(socket_fd, (struct sockaddr *)&address, sizeof(address)) != 0
    ) {
        (void)close(socket_fd);
        return -1;
    }
    return socket_fd;
}

static int read_response(int socket_fd, char *response, size_t capacity) {
    size_t used = 0;
    while (used < capacity - 1) {
        ssize_t received = recv(socket_fd, response + used, capacity - 1 - used, 0);
        if (received <= 0) break;
        used += (size_t)received;
    }
    response[used] = '\0';
    return (int)used;
}

static int backend_is_ready(void) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    static const char request[] =
        "GET /status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n";
    if (send(socket_fd, request, sizeof(request) - 1, 0) != (ssize_t)(sizeof(request) - 1)) {
        (void)close(socket_fd);
        return 0;
    }
    char response[4096] = {0};
    (void)read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return (
        strstr(response, "HTTP/1.0 200") != NULL &&
        strstr(response, "\"service\":\"KRONOS_BROWSER_V1\"") != NULL &&
        strstr(response, "\"provider\"") != NULL &&
        strstr(response, "\"analysis\"") != NULL
    );
}

static int open_workspace(void) {
    execl(
        "/usr/bin/open",
        "open",
        "-a",
        "Google Chrome",
        workspace_url,
        (char *)NULL
    );
    return 1;
}

static int show_alert(const char *title, const char *message) {
    char script[768];
    if (
        snprintf(
            script,
            sizeof(script),
            "display alert \"%s\" message \"%s\" as critical",
            title,
            message
        ) < 0
    ) {
        return 1;
    }
    execl("/usr/bin/osascript", "osascript", "-e", script, (char *)NULL);
    return 1;
}

static int show_not_ready(void) {
    return show_alert(
        "KRONOS is not ready",
        "The approved local Python environment was not found. Contact Engineering."
    );
}

static int show_restart_failed(void) {
    return show_alert(
        "KRONOS restart failed",
        "The existing KRONOS backend could not be stopped safely. It was not reused. Contact Engineering."
    );
}

static int valid_token(const char *token) {
    if (strlen(token) != 64) return 0;
    for (size_t index = 0; index < 64; ++index) {
        char value = token[index];
        if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

static int read_control_record(
    const char *control_path,
    pid_t *backend_pid,
    char token[65]
) {
    FILE *handle = fopen(control_path, "r");
    if (handle == NULL) return 0;
    struct stat metadata;
    if (
        fstat(fileno(handle), &metadata) != 0 ||
        !S_ISREG(metadata.st_mode) ||
        metadata.st_uid != getuid() ||
        (metadata.st_mode & 077) != 0
    ) {
        (void)fclose(handle);
        return 0;
    }
    char schema[64] = {0};
    char pid_line[32] = {0};
    char token_line[80] = {0};
    int read_ok = (
        fgets(schema, sizeof(schema), handle) != NULL &&
        fgets(pid_line, sizeof(pid_line), handle) != NULL &&
        fgets(token_line, sizeof(token_line), handle) != NULL
    );
    (void)fclose(handle);
    if (!read_ok) return 0;
    schema[strcspn(schema, "\r\n")] = '\0';
    pid_line[strcspn(pid_line, "\r\n")] = '\0';
    token_line[strcspn(token_line, "\r\n")] = '\0';
    char *end = NULL;
    errno = 0;
    long parsed_pid = strtol(pid_line, &end, 10);
    if (
        strcmp(schema, control_schema) != 0 ||
        errno != 0 ||
        end == pid_line ||
        *end != '\0' ||
        parsed_pid < 2 ||
        parsed_pid > INT_MAX ||
        !valid_token(token_line)
    ) {
        return 0;
    }
    *backend_pid = (pid_t)parsed_pid;
    (void)memcpy(token, token_line, 65);
    return 1;
}

static int request_graceful_shutdown(pid_t backend_pid, const char *token) {
    if (kill(backend_pid, 0) != 0) return 0;
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    char request[768];
    int length = snprintf(
        request,
        sizeof(request),
        "POST /control/shutdown HTTP/1.0\r\n"
        "Host: 127.0.0.1:8947\r\n"
        "X-Kronos-Backend-Pid: %ld\r\n"
        "X-Kronos-Restart-Token: %s\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n\r\n",
        (long)backend_pid,
        token
    );
    if (
        length < 1 ||
        (size_t)length >= sizeof(request) ||
        send(socket_fd, request, (size_t)length, 0) != (ssize_t)length
    ) {
        (void)close(socket_fd);
        return 0;
    }
    char response[2048] = {0};
    (void)read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return (
        strstr(response, "HTTP/1.0 202") != NULL &&
        strstr(response, "\"status\":\"STOPPING\"") != NULL
    );
}

static int wait_for_backend_stop(pid_t backend_pid) {
    for (int attempt = 0; attempt < 150; ++attempt) {
        int process_gone = (kill(backend_pid, 0) != 0 && errno == ESRCH);
        int socket_fd = connect_backend();
        if (socket_fd >= 0) (void)close(socket_fd);
        if (process_gone && socket_fd < 0) return 1;
        usleep(100000);
    }
    return 0;
}

static int start_backend(
    const char *repository,
    const char *python,
    const char *browser_entry,
    const char *python_path
) {
    pid_t child = fork();
    if (child < 0) return 0;
    if (child == 0) {
        if (setsid() < 0) _exit(1);
        pid_t grandchild = fork();
        if (grandchild < 0) _exit(1);
        if (grandchild > 0) _exit(0);

        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) {
            (void)dup2(devnull, STDIN_FILENO);
            (void)dup2(devnull, STDOUT_FILENO);
            (void)dup2(devnull, STDERR_FILENO);
            if (devnull > STDERR_FILENO) (void)close(devnull);
        }
        if (chdir(repository) != 0 || setenv("PYTHONPATH", python_path, 1) != 0) {
            _exit(1);
        }
        execl(python, python, browser_entry, "--no-browser", (char *)NULL);
        _exit(1);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        return 0;
    }
    for (int attempt = 0; attempt < 300; ++attempt) {
        if (backend_is_ready()) return 1;
        usleep(100000);
    }
    return 0;
}

int main(void) {
    const char *home = getenv("HOME");
    if (home == NULL || home[0] == '\0') return show_not_ready();

    char repository[PATH_MAX];
    char python[PATH_MAX];
    char browser_entry[PATH_MAX];
    char python_path[PATH_MAX * 2];
    char control_path[PATH_MAX];
    if (
        snprintf(repository, sizeof(repository), "%s/Documents/GitHub/Project-Kronos", home) < 0 ||
        snprintf(python, sizeof(python), "%s/.venv/bin/python", repository) < 0 ||
        snprintf(browser_entry, sizeof(browser_entry), "%s/tools/kronos_browser.py", repository) < 0 ||
        snprintf(python_path, sizeof(python_path), "%s/src:%s", repository, repository) < 0 ||
        snprintf(
            control_path,
            sizeof(control_path),
            "%s/Library/Application Support/KRONOS/runtime/browser-backend-v1.control",
            home
        ) < 0
    ) {
        return show_not_ready();
    }
    if (access(python, X_OK) != 0 || access(browser_entry, R_OK) != 0) {
        return show_not_ready();
    }

    int socket_connected = connect_backend();
    if (socket_connected >= 0) {
        (void)close(socket_connected);
        pid_t backend_pid = 0;
        char token[65] = {0};
        if (
            !read_control_record(control_path, &backend_pid, token) ||
            !request_graceful_shutdown(backend_pid, token) ||
            !wait_for_backend_stop(backend_pid)
        ) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_failed();
        }
        (void)memset(token, 0, sizeof(token));
    }

    if (!start_backend(repository, python, browser_entry, python_path)) {
        return show_restart_failed();
    }
    return open_workspace();
}
