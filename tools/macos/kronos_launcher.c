#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* APP-01A: an app location is authority only after resolving the actual image.
 * PACKAGE_VERIFY below is an inert build probe, never an operational bypass. */
static const char *canonical_bundle = "/Applications/KRONOS.app";
static const char *canonical_executable = "/Applications/KRONOS.app/Contents/MacOS/KRONOS";

static int canonical_image_path(const char *image) {
    char resolved_image[PATH_MAX];
    char resolved_canonical[PATH_MAX];
    struct stat metadata;
    if (image == NULL || realpath(image, resolved_image) == NULL ||
        realpath(canonical_executable, resolved_canonical) == NULL ||
        strcmp(resolved_canonical, canonical_executable) != 0 ||
        strcmp(resolved_image, canonical_executable) != 0 ||
        stat(resolved_image, &metadata) != 0 || !S_ISREG(metadata.st_mode)) return 0;
    return 1;
}

static int canonical_signature_valid(void) {
    pid_t child = fork();
    if (child < 0) return 0;
    if (child == 0) {
        execl("/usr/bin/codesign", "codesign", "--verify", "--deep", "--strict",
              "-R", "=identifier \"com.project-kronos.browser-v1\"",
              canonical_bundle, (char *)NULL);
        _exit(1);
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) return 0;
    }
    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

static int canonical_operational_image(void) {
    char image[PATH_MAX];
    uint32_t capacity = sizeof(image);
    return _NSGetExecutablePath(image, &capacity) == 0 &&
        canonical_image_path(image) && canonical_signature_valid();
}

static const char *workspace_script =
    "tell application \"Google Chrome\"\n"
    "repeat with browserWindow in windows\n"
    "set tabNumber to 0\n"
    "repeat with browserTab in tabs of browserWindow\n"
    "set tabNumber to tabNumber + 1\n"
    "if URL of browserTab starts with \"http://127.0.0.1:8947/\" then\n"
    "set active tab index of browserWindow to tabNumber\n"
    "set index of browserWindow to 1\n"
    "activate\n"
    "if URL of browserTab is \"http://127.0.0.1:8947/swing/opportunities\" then "
    "set URL of browserTab to \"http://127.0.0.1:8947/swing/opportunities\"\n"
    "return\n"
    "end if\n"
    "end repeat\n"
    "end repeat\n"
    "open location \"http://127.0.0.1:8947/swing/opportunities\"\n"
    "activate\n"
    "end tell";
static const char *control_schema = "KRONOS_BROWSER_BACKEND_CONTROL_V1";
#define BACKEND_STATUS_RESPONSE_BYTES (64 * 1024)

static int directory_exists(const char *path) {
    struct stat metadata;
    return stat(path, &metadata) == 0 && S_ISDIR(metadata.st_mode);
}

static int repository_is_governed(const char *repository) {
    char git_directory[PATH_MAX];
    char project_file[PATH_MAX];
    char python[PATH_MAX];
    char browser_entry[PATH_MAX];
    char package_directory[PATH_MAX];
    if (
        snprintf(git_directory, sizeof(git_directory), "%s/.git", repository) < 0 ||
        snprintf(project_file, sizeof(project_file), "%s/pyproject.toml", repository) < 0 ||
        snprintf(python, sizeof(python), "%s/.venv/bin/python", repository) < 0 ||
        snprintf(browser_entry, sizeof(browser_entry), "%s/tools/kronos_browser.py", repository) < 0 ||
        snprintf(package_directory, sizeof(package_directory), "%s/src/kronos", repository) < 0
    ) {
        return 0;
    }
    return (
        directory_exists(git_directory) &&
        access(project_file, R_OK) == 0 &&
        access(python, X_OK) == 0 &&
        access(browser_entry, R_OK) == 0 &&
        directory_exists(package_directory)
    );
}

static int discover_repository(const char *home, char repository[PATH_MAX]) {
    static const char *relative_roots[] = {
        "Documents/GitHub",
        "Developer",
        "Projects",
    };
    int matches = 0;
    for (size_t root_index = 0;
         root_index < sizeof(relative_roots) / sizeof(relative_roots[0]);
         ++root_index) {
        char root[PATH_MAX];
        if (snprintf(root, sizeof(root), "%s/%s", home, relative_roots[root_index]) < 0) {
            return 0;
        }
        DIR *directory = opendir(root);
        if (directory == NULL) continue;
        struct dirent *entry = NULL;
        while ((entry = readdir(directory)) != NULL) {
            if (entry->d_name[0] == '.') continue;
            char candidate[PATH_MAX];
            int length = snprintf(candidate, sizeof(candidate), "%s/%s", root, entry->d_name);
            if (
                length < 1 ||
                (size_t)length >= sizeof(candidate) ||
                !repository_is_governed(candidate)
            ) {
                continue;
            }
            ++matches;
            if (matches == 1) {
                (void)memcpy(repository, candidate, (size_t)length + 1);
            }
        }
        (void)closedir(directory);
    }
    return matches == 1;
}

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
    if (capacity < 2) return -1;
    size_t used = 0;
    int closed = 0;
    while (used < capacity - 1) {
        ssize_t received = recv(socket_fd, response + used, capacity - 1 - used, 0);
        if (received == 0) {
            closed = 1;
            break;
        }
        if (received < 0) {
            if (errno == EINTR) continue;
            response[0] = '\0';
            return -1;
        }
        used += (size_t)received;
    }
    if (!closed) {
        char extra = '\0';
        for (;;) {
            ssize_t received = recv(socket_fd, &extra, sizeof(extra), 0);
            if (received == 0) break;
            if (received > 0) {
                response[0] = '\0';
                return -1;
            }
            if (errno == EINTR) continue;
            response[0] = '\0';
            return -1;
        }
    }
    response[used] = '\0';
    if (used == 0 || memchr(response, '\0', used) != NULL) {
        response[0] = '\0';
        return -1;
    }
    const char *header_end = strstr(response, "\r\n\r\n");
    const char *line_end = strstr(response, "\r\n");
    if (header_end == NULL || line_end == NULL || line_end >= header_end) {
        response[0] = '\0';
        return -1;
    }
    size_t header_bytes = (size_t)(header_end + 4 - response);
    const char *line = line_end + 2;
    int content_length_found = 0;
    size_t content_length = 0;
    while (line < header_end) {
        line_end = strstr(line, "\r\n");
        if (line_end == NULL || line_end > header_end) {
            response[0] = '\0';
            return -1;
        }
        if ((size_t)(line_end - line) >= 15 &&
            strncmp(line, "Content-Length:", 15) == 0) {
            if (content_length_found) {
                response[0] = '\0';
                return -1;
            }
            const char *value = line + 15;
            while (value < line_end && (*value == ' ' || *value == '\t')) ++value;
            const char *first_digit = value;
            while (value < line_end && *value >= '0' && *value <= '9') {
                size_t digit = (size_t)(*value - '0');
                if (content_length > (((size_t)-1) - digit) / 10) {
                    response[0] = '\0';
                    return -1;
                }
                content_length = content_length * 10 + digit;
                ++value;
            }
            while (value < line_end && (*value == ' ' || *value == '\t')) ++value;
            if (value == first_digit || value != line_end) {
                response[0] = '\0';
                return -1;
            }
            content_length_found = 1;
        }
        line = line_end + 2;
    }
    if (!content_length_found || header_bytes > used ||
        content_length != used - header_bytes) {
        response[0] = '\0';
        return -1;
    }
    return (int)used;
}

static int response_is_ready(const char *response) {
    return (
        strncmp(response, "HTTP/1.0 200 ", 13) == 0 &&
        strstr(response, "\"service\":\"KRONOS_BROWSER_V1\"") != NULL &&
        strstr(response, "\"provider\"") != NULL &&
        strstr(response, "\"analysis\"") != NULL &&
        strstr(response, "\"runtime_ready\":true") != NULL
    );
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
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    int response_bytes = read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return response_bytes > 0 && response_is_ready(response);
}

static int open_workspace(void) {
    execl(
        "/usr/bin/osascript",
        "osascript",
        "-e",
        workspace_script,
        (char *)NULL
    );
    return 1;
}

static int acquire_launcher_lock(const char *repository) {
    int descriptor = open(repository, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (descriptor < 0) return -1;
    for (;;) {
        if (flock(descriptor, LOCK_EX) == 0) return descriptor;
        if (errno != EINTR) {
            (void)close(descriptor);
            return -1;
        }
    }
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

static int show_restart_blocked(void) {
    return show_alert(
        "KRONOS restart blocked",
        "The existing KRONOS backend could not be stopped through the authenticated maintenance handoff. No replacement was started. Contact Engineering."
    );
}

static int show_existing_backend_unhealthy(void) {
    return show_alert(
        "KRONOS is not ready",
        "A KRONOS backend already owns the local Browser address but is not ready. It was not restarted. Contact Engineering."
    );
}

static int show_replacement_child_exited(void) {
    return show_alert(
        "KRONOS replacement failed",
        "The previous backend stopped safely, but the replacement process exited before becoming ready. Do not relaunch KRONOS. Contact Engineering."
    );
}

static int show_replacement_ready_timeout(void) {
    return show_alert(
        "KRONOS is still starting",
        "The previous backend stopped safely and the replacement was started, but it did not become ready within 120 seconds. Do not relaunch KRONOS. Contact Engineering."
    );
}

static int show_replacement_internal_failure(void) {
    return show_alert(
        "KRONOS replacement failed",
        "The previous backend stopped safely, but the replacement could not be started or monitored safely. Do not relaunch KRONOS. Contact Engineering."
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

static int valid_revision(const char *revision) {
    if (revision == NULL || strlen(revision) != 40) return 0;
    for (size_t index = 0; index < 40; ++index) {
        char value = revision[index];
        if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

static int repository_revision_matches(const char *repository, const char *expected) {
    if (!valid_revision(expected)) return 0;
    int output[2];
    if (pipe(output) != 0) return 0;
    pid_t child = fork();
    if (child < 0) {
        (void)close(output[0]);
        (void)close(output[1]);
        return 0;
    }
    if (child == 0) {
        int devnull = open("/dev/null", O_WRONLY);
        if (
            chdir(repository) != 0 ||
            dup2(output[1], STDOUT_FILENO) < 0 ||
            (devnull >= 0 && dup2(devnull, STDERR_FILENO) < 0)
        ) {
            _exit(1);
        }
        (void)close(output[0]);
        (void)close(output[1]);
        if (devnull > STDERR_FILENO) (void)close(devnull);
        execl("/usr/bin/git", "git", "rev-parse", "HEAD", (char *)NULL);
        _exit(1);
    }
    (void)close(output[1]);
    char revision[42] = {0};
    size_t used = 0;
    while (used < sizeof(revision)) {
        ssize_t count = read(output[0], revision + used, sizeof(revision) - used);
        if (count == 0) break;
        if (count < 0) {
            if (errno == EINTR) continue;
            used = 0;
            break;
        }
        used += (size_t)count;
    }
    (void)close(output[0]);
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) return 0;
    }
    return WIFEXITED(status) && WEXITSTATUS(status) == 0 && used == 41 &&
        revision[40] == '\n' && memcmp(revision, expected, 40) == 0;
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

static int backend_is_reusable(const char *control_path) {
    if (!backend_is_ready()) return 0;
    pid_t backend_pid = 0;
    char token[65] = {0};
    int reusable = (
        read_control_record(control_path, &backend_pid, token) &&
        kill(backend_pid, 0) == 0
    );
    (void)memset(token, 0, sizeof(token));
    return reusable;
}

typedef enum ReplacementReadiness {
    REPLACEMENT_NOT_READY,
    REPLACEMENT_REQUIRED,
    REPLACEMENT_REQUIRED_OLD_CF55,
    REPLACEMENT_ALREADY_LOADED,
} ReplacementReadiness;

static const char *old_runtime_compatibility_revision =
    "cf55fa827b33d27ec44efb8988d413b1088ae07d";

static int read_backend_route(
    const char *path,
    char response[BACKEND_STATUS_RESPONSE_BYTES]
) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    char request[160];
    int request_bytes = snprintf(
        request,
        sizeof(request),
        "GET %s HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n",
        path
    );
    if (
        request_bytes < 1 ||
        (size_t)request_bytes >= sizeof(request) ||
        send(socket_fd, request, (size_t)request_bytes, 0) != request_bytes
    ) {
        (void)close(socket_fd);
        return 0;
    }
    int response_bytes = read_response(
        socket_fd,
        response,
        BACKEND_STATUS_RESPONSE_BYTES
    );
    (void)close(socket_fd);
    return response_bytes > 0 && strncmp(response, "HTTP/1.0 200 ", 13) == 0;
}

static int response_has_all(
    const char *response,
    const char *const required[],
    size_t count
) {
    for (size_t index = 0; index < count; ++index) {
        if (strstr(response, required[index]) == NULL) return 0;
    }
    return 1;
}

static int runtime_process_revision(
    const char *response,
    pid_t backend_pid,
    char revision[41]
) {
    char process_marker[96];
    int marker_bytes = snprintf(
        process_marker,
        sizeof(process_marker),
        "\"process\":{\"pid\":%ld,\"revision\":\"",
        (long)backend_pid
    );
    if (marker_bytes < 1 || (size_t)marker_bytes >= sizeof(process_marker)) return 0;
    const char *loaded = strstr(response, process_marker);
    if (loaded == NULL) return 0;
    loaded += (size_t)marker_bytes;
    if (strlen(loaded) < 41) return 0;
    (void)memcpy(revision, loaded, 40);
    revision[40] = '\0';
    return valid_revision(revision) && loaded[40] == '"';
}

static int maintenance_generation(const char *response, char generation[65]) {
    static const char marker[] =
        "\"maintenance\":{\"protocol\":\"KRONOS_MAINTENANCE_HANDOFF_V1\","
        "\"state\":\"INACTIVE\",\"active\":false,\"generation\":\"";
    const char *value = strstr(response, marker);
    if (value == NULL) return 0;
    value += sizeof(marker) - 1;
    if (strlen(value) < 65) return 0;
    (void)memcpy(generation, value, 64);
    generation[64] = '\0';
    return valid_token(generation) && value[64] == '"';
}

static int connection_is_quiescent(const char *response) {
    int connected = strstr(response, "\"rest_authentication\":\"CONNECTED\"") != NULL;
    int disconnected = strstr(response, "\"rest_authentication\":\"DISCONNECTED\"") != NULL;
    if ((!connected && !disconnected) || (connected && disconnected)) return 0;
    if (connected) {
        return
            strstr(response, "\"worker_active\":false,\"resources_pending\":false,\"cleanup_state\":\"COMPLETE\"") != NULL &&
            strstr(response, "\"restoration_worker_active\":false") != NULL;
    }
    return strstr(response, "\"connection_attempt\":null") != NULL;
}

static int runtime_shared_work_is_idle(const char *response) {
    static const char *required[] = {
        "\"startup\":\"READY\",\"failure\":null",
        "\"monitoring\":{\"schema\":\"KRONOS-SHARED-MONITORING-STATUS/1.0.0\",\"hub_state\":\"IDLE\",\"transport_state\":\"IDLE\",\"session_count\":0,\"active_session_count\":0,\"owner_count\":0,\"subscription_count\":0",
        "\"intraday_wo11_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"intraday_wo17_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"lifecycle_state\":\"IDLE\",\"shutdown_requested\":false,\"owned_workers\":0,\"worker_generation\":null,\"pass_active\":false",
        "\"swing_bulk_import\":{\"state\":\"IDLE\"",
        "\"batch_active\":false",
    };
    return response_has_all(response, required, sizeof(required) / sizeof(required[0])) &&
        connection_is_quiescent(response);
}

static int new_runtime_analysis_is_idle(const char *response) {
    static const char *required[] = {
        "\"analysis_work\":{\"state\":\"IDLE\",\"generation\":null,\"run_identity\":null,\"owned_work_count\":0",
        "\"analysis_execution\":{\"state\":\"IDLE\",\"pid\":null,\"generation\":null,\"failure\":null,\"failure_diagnostic\":null,\"owned_workers\":0",
    };
    return response_has_all(response, required, sizeof(required) / sizeof(required[0]));
}

static int old_status_analysis_is_idle(const char *response) {
    static const char *required[] = {
        "\"service\":\"KRONOS_BROWSER_V1\"",
        "\"analysis\":\"READY\"",
        "\"swing_publication\":{\"control\":" ,
        "\"analysis_work\":{\"state\":\"IDLE\",\"generation\":null,\"run_identity\":null,\"owned_work_count\":0",
        "\"analysis_execution\":{\"state\":\"IDLE\",\"pid\":null,\"generation\":null,\"failure\":null,\"failure_diagnostic\":null,\"owned_workers\":0",
        "\"runtime_ready\":true",
        "\"intraday_wo11_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"intraday_wo17_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"lifecycle_state\":\"IDLE\",\"shutdown_requested\":false,\"owned_workers\":0,\"worker_generation\":null,\"pass_active\":false",
        "\"swing_bulk_import\":{\"state\":\"IDLE\"",
        "\"batch_active\":false",
    };
    return response_has_all(response, required, sizeof(required) / sizeof(required[0]));
}

static ReplacementReadiness backend_replacement_readiness(
    pid_t backend_pid,
    const char *target_revision
) {
    if (backend_pid < 2 || !valid_revision(target_revision) || kill(backend_pid, 0) != 0) {
        return REPLACEMENT_NOT_READY;
    }
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    char loaded_revision[41] = {0};
    if (
        !read_backend_route("/runtime/status", response) ||
        !runtime_process_revision(response, backend_pid, loaded_revision)
    ) {
        return REPLACEMENT_NOT_READY;
    }
    if (strcmp(loaded_revision, target_revision) == 0) {
        return REPLACEMENT_ALREADY_LOADED;
    }
    if (!runtime_shared_work_is_idle(response)) return REPLACEMENT_NOT_READY;
    if (new_runtime_analysis_is_idle(response)) return REPLACEMENT_REQUIRED;
    if (strcmp(loaded_revision, old_runtime_compatibility_revision) != 0) {
        return REPLACEMENT_NOT_READY;
    }

    char first_generation[65] = {0};
    if (!maintenance_generation(response, first_generation)) return REPLACEMENT_NOT_READY;
    char status_response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    char status_generation[65] = {0};
    if (
        !read_backend_route("/status", status_response) ||
        !old_status_analysis_is_idle(status_response) ||
        !maintenance_generation(status_response, status_generation) ||
        strcmp(first_generation, status_generation) != 0
    ) {
        return REPLACEMENT_NOT_READY;
    }

    char recheck[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    char recheck_revision[41] = {0};
    char recheck_generation[65] = {0};
    if (
        !read_backend_route("/runtime/status", recheck) ||
        !runtime_process_revision(recheck, backend_pid, recheck_revision) ||
        strcmp(recheck_revision, loaded_revision) != 0 ||
        !runtime_shared_work_is_idle(recheck) ||
        new_runtime_analysis_is_idle(recheck) ||
        !maintenance_generation(recheck, recheck_generation) ||
        strcmp(first_generation, recheck_generation) != 0
    ) {
        return REPLACEMENT_NOT_READY;
    }
    return REPLACEMENT_REQUIRED_OLD_CF55;
}

static int backend_supports_maintenance(void) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    static const char request[] =
        "GET /status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n";
    if (send(socket_fd, request, sizeof(request) - 1, 0) != (ssize_t)(sizeof(request) - 1)) {
        (void)close(socket_fd);
        return 0;
    }
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    int response_bytes = read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return response_bytes > 0 &&
        strncmp(response, "HTTP/1.0 200 ", 13) == 0 &&
        strstr(response, "\"protocol\":\"KRONOS_MAINTENANCE_HANDOFF_V1\"") != NULL;
}

static int request_graceful_shutdown(pid_t backend_pid, const char *token, const char *generation) {
    /* Never stop a legacy backend that cannot mint the required handoff. */
    if (!backend_supports_maintenance()) return 0;
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
        "X-Kronos-Maintenance-Generation: %s\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n\r\n",
        (long)backend_pid,
        token,
        generation
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
    int response_bytes = read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return (
        response_bytes > 0 &&
        strncmp(response, "HTTP/1.0 202 ", 13) == 0 &&
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

static int qualify_source(const char *repository, const char *python) {
    char gate[PATH_MAX];
    if (snprintf(gate, sizeof(gate), "%s/tools/runtime_source_gate.py", repository) < 0) return 0;
    pid_t child = fork();
    if (child < 0) return 0;
    if (child == 0) {
        execl(python, python, "-B", gate, (char *)NULL);
        _exit(1);
    }
    int status = 0;
    return waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

typedef enum BackendStartResult {
    BACKEND_START_READY,
    BACKEND_START_CHILD_EXITED,
    BACKEND_START_READY_TIMEOUT,
    BACKEND_START_INTERNAL_FAILURE,
} BackendStartResult;

typedef struct BackendStartMonitor {
    int (*monotonic_now)(struct timespec *value);
    pid_t (*observe_child)(pid_t child, int *status);
    int (*ready)(void);
    int (*pause)(const struct timespec *duration, struct timespec *remaining);
} BackendStartMonitor;

#define BACKEND_START_READY_TIMEOUT_SECONDS 120
#define BACKEND_START_POLL_NANOSECONDS 100000000L

static int monotonic_now(struct timespec *value) {
    return clock_gettime(CLOCK_MONOTONIC, value);
}

static pid_t observe_backend_child(pid_t child, int *status) {
    return waitpid(child, status, WNOHANG);
}

static int pause_backend_monitor(
    const struct timespec *duration,
    struct timespec *remaining
) {
    return nanosleep(duration, remaining);
}

static const BackendStartMonitor production_backend_start_monitor = {
    .monotonic_now = monotonic_now,
    .observe_child = observe_backend_child,
    .ready = backend_is_ready,
    .pause = pause_backend_monitor,
};

static int time_reached(
    const struct timespec *value,
    const struct timespec *deadline
) {
    return value->tv_sec > deadline->tv_sec ||
        (value->tv_sec == deadline->tv_sec && value->tv_nsec >= deadline->tv_nsec);
}

static struct timespec time_until(
    const struct timespec *value,
    const struct timespec *deadline
) {
    struct timespec remaining = {
        .tv_sec = deadline->tv_sec - value->tv_sec,
        .tv_nsec = deadline->tv_nsec - value->tv_nsec,
    };
    if (remaining.tv_nsec < 0) {
        --remaining.tv_sec;
        remaining.tv_nsec += 1000000000L;
    }
    if (remaining.tv_sec > 0 || remaining.tv_nsec > BACKEND_START_POLL_NANOSECONDS) {
        remaining.tv_sec = 0;
        remaining.tv_nsec = BACKEND_START_POLL_NANOSECONDS;
    }
    return remaining;
}

static BackendStartResult monitor_backend_start(
    pid_t child,
    int timeout_seconds,
    const BackendStartMonitor *monitor
) {
    if (
        monitor == NULL ||
        monitor->monotonic_now == NULL ||
        monitor->observe_child == NULL ||
        monitor->ready == NULL ||
        monitor->pause == NULL ||
        timeout_seconds < 1
    ) {
        return BACKEND_START_INTERNAL_FAILURE;
    }

    struct timespec started;
    if (monitor->monotonic_now(&started) != 0) {
        return BACKEND_START_INTERNAL_FAILURE;
    }
    struct timespec deadline = started;
    deadline.tv_sec += timeout_seconds;

    for (;;) {
        int status = 0;
        errno = 0;
        pid_t observed = monitor->observe_child(child, &status);
        if (observed == child) return BACKEND_START_CHILD_EXITED;
        if (observed != 0 && !(observed < 0 && errno == EINTR)) {
            return BACKEND_START_INTERNAL_FAILURE;
        }

        struct timespec current;
        if (monitor->monotonic_now(&current) != 0) {
            return BACKEND_START_INTERNAL_FAILURE;
        }
        if (time_reached(&current, &deadline)) {
            return BACKEND_START_READY_TIMEOUT;
        }
        if (monitor->ready()) return BACKEND_START_READY;

        struct timespec duration = time_until(&current, &deadline);
        struct timespec remaining;
        if (monitor->pause(&duration, &remaining) != 0 && errno != EINTR) {
            return BACKEND_START_INTERNAL_FAILURE;
        }
    }
}

static BackendStartResult start_backend(
    const char *repository,
    const char *python,
    const char *browser_entry,
    const char *python_path,
    pid_t previous_pid,
    const char *previous_token,
    const char *generation
) {
    pid_t child = fork();
    if (child < 0) return BACKEND_START_INTERNAL_FAILURE;
    if (child == 0) {
        if (setsid() < 0) _exit(1);
        /* Keep the canonical parent alive until the backend qualifies itself. */

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
        if (previous_pid > 0) {
            char parent[32];
            (void)snprintf(parent, sizeof(parent), "%ld", (long)previous_pid);
            if (setenv("KRONOS_MAINTENANCE_GENERATION", generation, 1) != 0 ||
                setenv("KRONOS_MAINTENANCE_PARENT", parent, 1) != 0 ||
                setenv("KRONOS_MAINTENANCE_PROOF", previous_token, 1) != 0) _exit(1);
        } else {
            (void)unsetenv("KRONOS_MAINTENANCE_GENERATION");
            (void)unsetenv("KRONOS_MAINTENANCE_PARENT");
            (void)unsetenv("KRONOS_MAINTENANCE_PROOF");
        }
        const char *launch_mode = getenv("KRONOS_LAUNCH_MODE");
        if (
            launch_mode != NULL && strcmp(launch_mode, "GOVERNED_REPLACEMENT") == 0 &&
            (unsetenv("KRONOS_LAUNCH_MODE") != 0 ||
             unsetenv("KRONOS_REPLACEMENT_REVISION") != 0)
        ) _exit(1);
        execl(python, python, "-B", browser_entry, "--no-browser", (char *)NULL);
        _exit(1);
    }
    return monitor_backend_start(
        child,
        BACKEND_START_READY_TIMEOUT_SECONDS,
        &production_backend_start_monitor
    );
}

int main(void) {
    const char *mode = getenv("KRONOS_LAUNCH_MODE");
    /* Signed-package execution check: no filesystem, runtime, or Browser action. */
    if (mode != NULL && strcmp(mode, "PACKAGE_VERIFY") == 0) {
        puts("KRONOS_LAUNCHER_PACKAGE_V1_OK");
        return 0;
    }
    if (!canonical_operational_image()) return 1;
    int bootstrap = mode != NULL && strcmp(mode, "LEGACY_BOOTSTRAP") == 0;
    int replacement = mode != NULL && strcmp(mode, "GOVERNED_REPLACEMENT") == 0;
    const char *target_revision = getenv("KRONOS_REPLACEMENT_REVISION");
    const char *migration = getenv("KRONOS_LEGACY_BOOTSTRAP_ID");
    const char *migration_proof = getenv("KRONOS_LEGACY_BOOTSTRAP_PROOF");
    if ((mode != NULL && !bootstrap && !replacement) ||
        (!bootstrap && (migration != NULL || migration_proof != NULL))) return 1;
    if (bootstrap && (migration == NULL || migration_proof == NULL ||
        strlen(migration) != 64 || strlen(migration_proof) != 64 ||
        strspn(migration, "0123456789abcdef") != 64 ||
        strspn(migration_proof, "0123456789abcdef") != 64 ||
        getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
        getenv("KRONOS_MAINTENANCE_PARENT") != NULL ||
        getenv("KRONOS_MAINTENANCE_PROOF") != NULL)) return 1;
    if (
        (replacement && (
            !valid_revision(target_revision) ||
            migration != NULL || migration_proof != NULL ||
            getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
            getenv("KRONOS_MAINTENANCE_PARENT") != NULL ||
            getenv("KRONOS_MAINTENANCE_PROOF") != NULL
        )) ||
        (!replacement && target_revision != NULL)
    ) return 1;
    const char *home = getenv("HOME");
    if (home == NULL || home[0] == '\0') return show_not_ready();

    char repository[PATH_MAX];
    char python[PATH_MAX];
    char browser_entry[PATH_MAX];
    char python_path[PATH_MAX * 2];
    char control_path[PATH_MAX];
    if (
        !discover_repository(home, repository) ||
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

    /* The read-only source gate precedes every probe or runtime transition. */
    if (!qualify_source(repository, python)) return show_alert(
        "KRONOS source qualification failed",
        "A clean published develop revision and verified source proof are required. No runtime transition was started. Contact Engineering."
    );
    if (replacement && !repository_revision_matches(repository, target_revision)) {
        return show_alert(
            "KRONOS replacement blocked",
            "The requested replacement revision is not the exact clean published source. No runtime transition was started. Contact Engineering."
        );
    }

    /* Serialize the probe/start decision without creating or rewriting a file. */
    int launcher_lock = acquire_launcher_lock(repository);
    if (launcher_lock < 0) return show_alert(
        "KRONOS launch blocked",
        "The launcher could not establish single-flight ownership. No runtime transition was started. Contact Engineering."
    );

    /* An ordinary Dock click is inert access to one already-ready shared runtime. */
    if (!bootstrap && !replacement && backend_is_reusable(control_path)) return open_workspace();

    pid_t backend_pid = 0;
    char token[65] = {0};
    if (replacement) {
        if (!read_control_record(control_path, &backend_pid, token)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        ReplacementReadiness readiness = backend_replacement_readiness(
            backend_pid,
            target_revision
        );
        if (readiness == REPLACEMENT_ALREADY_LOADED) {
            (void)memset(token, 0, sizeof(token));
            return open_workspace();
        }
        if (
            readiness != REPLACEMENT_REQUIRED &&
            readiness != REPLACEMENT_REQUIRED_OLD_CF55
        ) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        puts(
            readiness == REPLACEMENT_REQUIRED_OLD_CF55
                ? "KRONOS_REPLACEMENT_PREDICATE=OLD_RUNTIME_CF55_STATUS_PAIR"
                : "KRONOS_REPLACEMENT_PREDICATE=CURRENT_RUNTIME_STATUS"
        );
        (void)fflush(stdout);
    }
    char generation[65] = {0};
    unsigned char random_bytes[32];
    arc4random_buf(random_bytes, sizeof(random_bytes));
    for (size_t i = 0; i < sizeof(random_bytes); ++i)
        (void)snprintf(generation + i * 2, 3, "%02x", random_bytes[i]);
    int socket_connected = connect_backend();
    if (socket_connected >= 0) {
        (void)close(socket_connected);
        if (!bootstrap && !replacement) return show_existing_backend_unhealthy();
        if (
            (!replacement && !read_control_record(control_path, &backend_pid, token)) ||
            !request_graceful_shutdown(backend_pid, token, generation) ||
            !wait_for_backend_stop(backend_pid)
        ) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
    } else if (replacement) {
        (void)memset(token, 0, sizeof(token));
        return show_restart_blocked();
    }

    BackendStartResult start_result = start_backend(
        repository,
        python,
        browser_entry,
        python_path,
        backend_pid,
        token,
        generation
    );
    (void)memset(token, 0, sizeof(token));
    switch (start_result) {
        case BACKEND_START_READY:
            return bootstrap ? 0 : open_workspace();
        case BACKEND_START_CHILD_EXITED:
            return show_replacement_child_exited();
        case BACKEND_START_READY_TIMEOUT:
            return show_replacement_ready_timeout();
        case BACKEND_START_INTERNAL_FAILURE:
            return show_replacement_internal_failure();
    }
    return show_replacement_internal_failure();
}
