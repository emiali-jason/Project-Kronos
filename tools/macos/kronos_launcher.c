#include <arpa/inet.h>
#include <CommonCrypto/CommonDigest.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <netinet/in.h>
#include <poll.h>
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
#define HANDOFF_SECONDS 45
/* Non-null only while monitoring an explicitly authorized recovery successor. */
static const struct timespec *recovery_io_deadline=NULL;

static int recovery_wait_io(int fd,short events,const struct timespec *deadline) {
    for(;;){
        struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
        long long remaining=(long long)(deadline->tv_sec-now.tv_sec)*1000000000LL+deadline->tv_nsec-now.tv_nsec;
        if(remaining<=0)return 0;
        long long milliseconds=(remaining+999999)/1000000;
        struct pollfd item={.fd=fd,.events=events};
        int result=poll(&item,1,milliseconds>INT_MAX?INT_MAX:(int)milliseconds);
        if(result<0&&errno==EINTR)continue;
        return result>0 && !(item.revents&POLLNVAL);
    }
}

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
        if(recovery_io_deadline && !recovery_wait_io(socket_fd,POLLIN,recovery_io_deadline))return -1;
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
            if(recovery_io_deadline && !recovery_wait_io(socket_fd,POLLIN,recovery_io_deadline))return -1;
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

static int new_runtime_is_drainable(const char *response) {
    static const char *required[] = {
        "\"maintenance_drain\":{\"state\":\"OPEN\",\"generation\":null,\"owners\":",
        "\"maintenance_claim\":\"DRAINABLE\"",
        "\"startup\":\"READY\",\"failure\":null",
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
    if (new_runtime_is_drainable(response)) return REPLACEMENT_REQUIRED;
    if (!runtime_shared_work_is_idle(response)) return REPLACEMENT_NOT_READY;
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
        new_runtime_is_drainable(recheck) ||
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

static int request_graceful_shutdown(pid_t backend_pid, const char *token,
                                     const char *generation, int require_v2) {
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
        strstr(response, require_v2 ? "\"status\":\"DRAINING\"" :
               "\"status\":\"STOPPING\"") != NULL
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

static int cold_start_has_no_control_or_live_handoff(const char *control_path) {
    struct stat metadata;
    if (lstat(control_path, &metadata) == 0 || errno != ENOENT) return 0;
    char directory_path[PATH_MAX];
    int length = snprintf(directory_path, sizeof(directory_path), "%s", control_path);
    if (length < 1 || (size_t)length >= sizeof(directory_path)) return 0;
    char *separator = strrchr(directory_path, '/');
    if (separator == NULL) return 0;
    (void)strcpy(separator + 1, "maintenance");
    if (lstat(directory_path, &metadata) != 0) return errno == ENOENT;
    if (!S_ISDIR(metadata.st_mode) || metadata.st_uid != getuid() ||
        (metadata.st_mode & 077) != 0) return 0;
    DIR *directory = opendir(directory_path);
    if (directory == NULL) return 0;
    time_t now = time(NULL);
    int safe = now != (time_t)-1;
    struct dirent *entry;
    while (safe && (entry = readdir(directory)) != NULL) {
        if (strlen(entry->d_name) != 69 ||
            strcmp(entry->d_name + 64, ".json") != 0) continue;
        char generation[65];
        (void)memcpy(generation, entry->d_name, 64);
        generation[64] = '\0';
        if (!valid_token(generation)) continue;
        char source[PATH_MAX];
        char consumed[PATH_MAX];
        if (snprintf(source, sizeof(source), "%s/%s", directory_path, entry->d_name) < 1 ||
            snprintf(consumed, sizeof(consumed), "%s/%s.consumed.json", directory_path,
                     generation) < 1 || lstat(source, &metadata) != 0 ||
            !S_ISREG(metadata.st_mode)) { safe = 0; break; }
        if (metadata.st_mtime > now || now - metadata.st_mtime <= HANDOFF_SECONDS) {
            if (lstat(consumed, &metadata) != 0 || !S_ISREG(metadata.st_mode)) {
                safe = 0;
                break;
            }
        }
    }
    (void)closedir(directory);
    return safe;
}

static int verify_v2_handoff(
    const char *repository, const char *python, const char *python_path,
    const char *control_path, const char *generation, pid_t parent_pid,
    const char *parent_revision, const char *proof
) {
    char maintenance_path[PATH_MAX];
    char parent[32];
    int length = snprintf(maintenance_path, sizeof(maintenance_path),
                          "%s", control_path);
    if (length < 1 || (size_t)length >= sizeof(maintenance_path)) return 0;
    /* control_path names a file; use its parent, not a child of the file. */
    char *separator = strrchr(maintenance_path, '/');
    if (separator == NULL) return 0;
    (void)strcpy(separator + 1, "maintenance");
    if (snprintf(parent, sizeof(parent), "%ld", (long)parent_pid) < 1) return 0;
    int input[2];
    if (pipe(input) != 0) return 0;
    pid_t child = fork();
    if (child < 0) {
        (void)close(input[0]);
        (void)close(input[1]);
        return 0;
    }
    if (child == 0) {
        int devnull = open("/dev/null", O_WRONLY);
        if (chdir(repository) != 0 || setenv("PYTHONPATH", python_path, 1) != 0 ||
            dup2(input[0], STDIN_FILENO) < 0 ||
            (devnull >= 0 && dup2(devnull, STDOUT_FILENO) < 0) ||
            (devnull >= 0 && dup2(devnull, STDERR_FILENO) < 0)) _exit(1);
        (void)close(input[0]);
        (void)close(input[1]);
        if (devnull > STDERR_FILENO) (void)close(devnull);
        execl(python, python, "-B", "-m", "kronos.common.maintenance",
              "verify-v2", maintenance_path, generation, parent,
              parent_revision, (char *)NULL);
        _exit(1);
    }
    (void)close(input[0]);
    struct sigaction ignore_pipe = {0};
    struct sigaction previous_pipe = {0};
    ignore_pipe.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &ignore_pipe, &previous_pipe) != 0) {
        (void)close(input[1]);
        (void)waitpid(child, NULL, 0);
        return 0;
    }
    size_t remaining = strlen(proof);
    while (remaining) {
        ssize_t written = write(input[1], proof + 64 - remaining, remaining);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) break;
        remaining -= (size_t)written;
    }
    (void)close(input[1]);
    (void)sigaction(SIGPIPE, &previous_pipe, NULL);
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) return 0;
    }
    return remaining == 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0;
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

/* ADR-0061: launcher-owned recovery permission. This is not Python authority. */
#define RECOVERY_CLASS "FAILED_ACTIVE_RECOVERY_REPLACEMENT"
#define RECOVERY_SCHEMA "KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/1.0.0"
#define RECOVERY_CAPABILITY "WO06H-CAPABILITY-9104752f2f4028b169cd5bcc249477024eb67b1ab2351a30415e40e5fa7e6e40"
/* The immutable owner-reviewed artifact and its canonical EpochStore bytes are
 * separate identities. Exact semantic-equivalence provenance is retained with
 * the release evidence; only RECOVERY_RELATION is production byte authority. */
#define RECOVERY_REVIEW_ARTIFACT_SHA256 "e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e"
#define RECOVERY_RELATION "707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b"
#define RECOVERY_DIAGNOSIS "3af1be040e466580111b4e5664d5177aa016aea58988a41cf8189d117931c25c"
#define RECOVERY_PREDECESSOR "cbe496e31d466eb28b7b710ffe9231b4324b1137"
#define RECOVERY_WINDOW_START "2026-09-12T07:50:33.006722+05:30"
#define RECOVERY_WINDOW_END "2026-10-12T07:50:33.006722+05:30"
#define RECOVERY_START_US 1789179633006722LL
#define RECOVERY_END_US 1791771633006722LL
#define RECOVERY_JSON_TOKENS 8192

typedef struct RecoveryJsonToken { int start, end, next, count; char kind; } RecoveryJsonToken;
typedef struct RecoveryJson {
    const char *text; int length, used; RecoveryJsonToken token[RECOVERY_JSON_TOKENS];
} RecoveryJson;

/* Closed, bounded JSON parser. Duplicate/escaped object keys and invalid JSON
 * are rejected; a marker hidden in a string or another object is never authority. */
static void recovery_json_space(const char *s, int *p) {
    while (s[*p] == ' ' || s[*p] == '\n' || s[*p] == '\r' || s[*p] == '\t') ++*p;
}
static int recovery_json_equal(const RecoveryJson *j, int t, const char *s) {
    return t >= 0 && j->token[t].end-j->token[t].start == (int)strlen(s) &&
        memcmp(j->text+j->token[t].start,s,strlen(s)) == 0;
}
static int recovery_json_parse(RecoveryJson *j, int *p, int depth) {
    recovery_json_space(j->text,p);
    if (*p >= j->length || depth > 32 || j->used >= RECOVERY_JSON_TOKENS) return -1;
    int t=j->used++; RecoveryJsonToken *r=&j->token[t]; memset(r,0,sizeof(*r));
    r->start=*p; char c=j->text[*p];
    if (c=='{' || c=='[') {
        r->kind=c; ++*p; recovery_json_space(j->text,p);
        char close=c=='{'?'}':']';
        if (j->text[*p]!=close) for (;;) {
            if (c=='{') {
                int key=recovery_json_parse(j,p,depth+1);
                if (key<0 || j->token[key].kind!='s' ||
                    memchr(j->text+j->token[key].start,'\\',j->token[key].end-j->token[key].start)) return -1;
                for (int k=t+1;k<key;k=j->token[j->token[k].next].next)
                    if (j->token[k].end-j->token[k].start == j->token[key].end-j->token[key].start &&
                        memcmp(j->text+j->token[k].start,j->text+j->token[key].start,
                               j->token[k].end-j->token[k].start)==0) return -1;
                recovery_json_space(j->text,p); if (j->text[(*p)++]!=':') return -1;
            }
            if (recovery_json_parse(j,p,depth+1)<0) return -1;
            ++r->count; recovery_json_space(j->text,p);
            if (j->text[*p]==close) break;
            if (j->text[(*p)++]!=',') return -1;
        }
        ++*p;
    } else if (c=='"') {
        r->kind='s'; r->start=++*p;
        while (*p<j->length && j->text[*p]!='"') {
            unsigned char v=(unsigned char)j->text[(*p)++]; if (v<32) return -1;
            if (v=='\\') {
                if (*p>=j->length) return -1;
                char esc=j->text[(*p)++];
                if (esc=='u') { for (int n=0;n<4;n++) {
                    if (*p>=j->length) return -1;
                    char h=j->text[(*p)++]; if (!strchr("0123456789abcdefABCDEF",h) || !h) return -1;
                }} else if (!esc || !strchr("\"\\/bfnrt",esc)) return -1;
            }
        }
        if (*p>=j->length) return -1;
        r->end=(*p)++;
    } else {
        r->kind='v'; int start=*p;
        while (*p<j->length && !strchr(" ,\t\r\n}]",j->text[*p])) ++*p;
        int size=*p-start;
        if (!((size==4 && (!memcmp(j->text+start,"true",4) || !memcmp(j->text+start,"null",4))) ||
              (size==5 && !memcmp(j->text+start,"false",5)))) {
            int q=start; if(j->text[q]=='-') ++q;
            if(j->text[q]=='0') ++q; else {
                if(j->text[q]<'1'||j->text[q]>'9') return -1;
                while(j->text[q]>='0'&&j->text[q]<='9') ++q;
            }
            if(j->text[q]=='.') { ++q; int a=q; while(j->text[q]>='0'&&j->text[q]<='9')++q; if(a==q)return -1; }
            if(j->text[q]=='e'||j->text[q]=='E') { ++q;if(j->text[q]=='+'||j->text[q]=='-')++q;
                int a=q;while(j->text[q]>='0'&&j->text[q]<='9')++q;if(a==q)return -1; }
            if(q!=*p) return -1;
        }
    }
    if (r->kind!='s') r->end=*p;
    r->next=j->used; return t;
}
static int recovery_json_document(RecoveryJson *j,const char *text) {
    memset(j,0,sizeof(*j));j->text=text;j->length=(int)strlen(text);int p=0;
    if(recovery_json_parse(j,&p,0)!=0 || j->token[0].kind!='{') return 0;
    recovery_json_space(text,&p);return p==j->length;
}
static int recovery_json_get(const RecoveryJson *j,int object,const char *key) {
    if(object<0 || j->token[object].kind!='{')return -1;
    for(int k=object+1;k<j->token[object].next;k=j->token[j->token[k].next].next)
        if(recovery_json_equal(j,k,key))return j->token[k].next;
    return -1;
}
static int recovery_field(const RecoveryJson *j,int obj,const char *key,const char *value) {
    int t=recovery_json_get(j,obj,key);
    char kind=(!strcmp(value,"true") || !strcmp(value,"false") || !strcmp(value,"null"))?'v':'s';
    return t>=0 && j->token[t].kind==kind && recovery_json_equal(j,t,value);
}
static int recovery_string(const RecoveryJson *j,int obj,const char *key,char *out,size_t cap) {
    int t=recovery_json_get(j,obj,key);if(t<0 || j->token[t].kind!='s')return 0;
    int n=j->token[t].end-j->token[t].start;
    if(n<1 || (size_t)n>=cap || memchr(j->text+j->token[t].start,'\\',(size_t)n))return 0;
    memcpy(out,j->text+j->token[t].start,(size_t)n);out[n]=0;return 1;
}
static long long recovery_integer(const RecoveryJson *j,int obj,const char *key) {
    int t=recovery_json_get(j,obj,key);char buf[32];if(t<0 || j->token[t].kind!='v')return -1;
    int n=j->token[t].end-j->token[t].start;if(n<1 || n>=31)return -1;
    memcpy(buf,j->text+j->token[t].start,(size_t)n);buf[n]=0;char *end=NULL;errno=0;
    long long v=strtoll(buf,&end,10);return errno || *end || v<0 ? -1:v;
}
static long long recovery_now_us(void) {
    struct timeval t;if(gettimeofday(&t,NULL)!=0)return -1;
    return (long long)t.tv_sec*1000000+t.tv_usec;
}
static int recovery_safe_path(const char *path,int directory,int private_mode) {
    char real[PATH_MAX],ancestor[PATH_MAX];struct stat s;
    if(!path || path[0]!='/' || strlen(path)>=PATH_MAX || !realpath(path,real) || strcmp(path,real))return 0;
    strcpy(ancestor,path);
    for (;;) {
        if(lstat(ancestor,&s)!=0 || S_ISLNK(s.st_mode))return 0;
        char *slash=strrchr(ancestor,'/');if(slash==ancestor)break;*slash=0;
    }
    if(lstat(path,&s)!=0 || s.st_uid!=getuid() || (directory?!S_ISDIR(s.st_mode):!S_ISREG(s.st_mode)))return 0;
    return !private_mode || (s.st_mode&077)==0;
}
static int recovery_separate_bundle(const char *rollback, const char *installed) {
    struct stat a,b;
    return recovery_safe_path(rollback,1,0) && recovery_safe_path(installed,1,0) &&
        strcmp(rollback,installed) && stat(rollback,&a)==0 && stat(installed,&b)==0 &&
        (a.st_dev!=b.st_dev || a.st_ino!=b.st_ino);
}
static int recovery_read_file(const char *path,char *out,size_t capacity,int private_mode) {
    if(!recovery_safe_path(path,0,private_mode))return 0;
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;struct stat s;
    int ok=fstat(fd,&s)==0 && S_ISREG(s.st_mode) && s.st_uid==getuid() &&
        (!private_mode || !(s.st_mode&077)) && s.st_size>0 && (size_t)s.st_size<capacity;
    size_t used=0;
    while(ok && used<(size_t)s.st_size) {ssize_t n=read(fd,out+used,(size_t)s.st_size-used);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=0;break;}used+=(size_t)n;}
    char extra; if(ok && read(fd,&extra,1)!=0)ok=0;close(fd);
    if(!ok || memchr(out,0,used))return 0;out[used]=0;return 1;
}
static int recovery_file_digest(const char *path,char out[65],int private_mode) {
    if(!recovery_safe_path(path,0,private_mode))return 0;
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;struct stat s;
    if(fstat(fd,&s)!=0 || !S_ISREG(s.st_mode) || s.st_uid!=getuid() ||
       (private_mode && (s.st_mode&077))){close(fd);return 0;}
    CC_SHA256_CTX context;CC_SHA256_Init(&context);unsigned char buffer[16384],digest[32];ssize_t n;
    while((n=read(fd,buffer,sizeof(buffer)))!=0){if(n<0){if(errno==EINTR)continue;close(fd);return 0;}
        CC_SHA256_Update(&context,buffer,(CC_LONG)n);}
    close(fd);CC_SHA256_Final(digest,&context);
    for(int i=0;i<32;i++)snprintf(out+2*i,3,"%02x",digest[i]);return 1;
}
static int recovery_control_record(const char *path,pid_t *pid,char token[65]) {
    char raw[256],expected[256];long parsed=0;char proof[65]={0};
    if(!recovery_read_file(path,raw,sizeof(raw),1) ||
       sscanf(raw,"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%64[0-9a-f]",&parsed,proof)!=2 ||
       parsed<2 || parsed>INT_MAX || !valid_token(proof))return 0;
    snprintf(expected,sizeof(expected),"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%s\n",parsed,proof);
    if(strcmp(raw,expected)){memset(proof,0,sizeof(proof));return 0;}
    *pid=(pid_t)parsed;memcpy(token,proof,65);memset(proof,0,sizeof(proof));return 1;
}

typedef struct RecoveryAuthorization {
    char attempt[65],file[PATH_MAX],root[PATH_MAX],digest[65],maintenance[65];
    char predecessor[41],successor[41],control_digest[65],package[65];
    char rollback[PATH_MAX],rollback_identity[65],relation[PATH_MAX],diagnosis[PATH_MAX];
    char sponsor[PATH_MAX],sponsor_digest[65],control[PATH_MAX];
    long long valid_from,valid_until,reserved_at;pid_t pid;
} RecoveryAuthorization;

static int recovery_load_authorization(const char *root,const char *attempt,
                                      const char *control,pid_t pid,const char *target,
                                      long long now,RecoveryAuthorization *a) {
    if(!valid_token(attempt) || !valid_revision(target) || pid<2 ||
       !recovery_safe_path(root,1,1))return 0;
    memset(a,0,sizeof(*a));strcpy(a->root,root);strcpy(a->attempt,attempt);
    if(snprintf(a->file,sizeof(a->file),"%s/%s.authorization.json",root,attempt)>=(int)sizeof(a->file))return 0;
    char raw[16384],reference[256],sponsor_path[PATH_MAX],sponsor_hash[65],actual[65];RecoveryJson j;
    if(!recovery_read_file(a->file,raw,sizeof(raw),1) || !recovery_json_document(&j,raw) || j.token[0].count!=24 ||
       !recovery_field(&j,0,"schema",RECOVERY_SCHEMA) || !recovery_field(&j,0,"recovery_class",RECOVERY_CLASS) ||
       !recovery_field(&j,0,"state","SPONSOR_APPROVED") || !recovery_field(&j,0,"attempt_identity",attempt) ||
       !recovery_string(&j,0,"sponsor_authorization_reference",reference,sizeof(reference)) ||
       !recovery_string(&j,0,"sponsor_authorization_path",sponsor_path,sizeof(sponsor_path)) ||
       !recovery_string(&j,0,"sponsor_authorization_sha256",sponsor_hash,sizeof(sponsor_hash)) || !valid_token(sponsor_hash) ||
       !recovery_file_digest(sponsor_path,actual,0) || strcmp(actual,sponsor_hash) ||
       !recovery_field(&j,0,"predecessor_revision",RECOVERY_PREDECESSOR) ||
       !recovery_field(&j,0,"successor_revision",target) ||
       !recovery_field(&j,0,"expected_successor_capability",RECOVERY_CAPABILITY) ||
       !recovery_field(&j,0,"compatibility_relation_sha256",RECOVERY_RELATION) ||
       !recovery_field(&j,0,"diagnosis_sha256",RECOVERY_DIAGNOSIS) ||
       !recovery_field(&j,0,"window_start",RECOVERY_WINDOW_START) || !recovery_field(&j,0,"window_end",RECOVERY_WINDOW_END) ||
       recovery_integer(&j,0,"predecessor_pid")!=pid ||
       !recovery_string(&j,0,"predecessor_maintenance_identity",a->maintenance,sizeof(a->maintenance)) || !valid_token(a->maintenance) ||
       !recovery_string(&j,0,"private_control_sha256",a->control_digest,sizeof(a->control_digest)) || !valid_token(a->control_digest) ||
       !recovery_file_digest(control,actual,1) || strcmp(actual,a->control_digest) ||
       !recovery_string(&j,0,"installed_package_identity",a->package,sizeof(a->package)) || !valid_token(a->package) ||
       !recovery_string(&j,0,"rollback_bundle",a->rollback,sizeof(a->rollback)) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_string(&j,0,"rollback_package_identity",a->rollback_identity,sizeof(a->rollback_identity)) || !valid_token(a->rollback_identity) ||
       !recovery_string(&j,0,"relation_path",a->relation,sizeof(a->relation)) ||
       !recovery_file_digest(a->relation,actual,0) || strcmp(actual,RECOVERY_RELATION) ||
       !recovery_string(&j,0,"diagnosis_path",a->diagnosis,sizeof(a->diagnosis)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,RECOVERY_DIAGNOSIS) ||
       !recovery_file_digest(a->file,a->digest,1))return 0;
    unsigned char parsed_digest[CC_SHA256_DIGEST_LENGTH]; char parsed_hex[65];
    CC_SHA256(raw,(CC_LONG)strlen(raw),parsed_digest);
    for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)snprintf(parsed_hex+2*i,3,"%02x",parsed_digest[i]);
    if(strcmp(parsed_hex,a->digest))return 0;
    a->valid_from=recovery_integer(&j,0,"valid_from_us");a->valid_until=recovery_integer(&j,0,"valid_until_us");
    if(a->valid_from<0 || a->valid_until<=a->valid_from || a->valid_until>RECOVERY_END_US ||
       now<RECOVERY_START_US || now>=RECOVERY_END_US || now<a->valid_from || now>=a->valid_until)return 0;
    a->pid=pid;strcpy(a->predecessor,RECOVERY_PREDECESSOR);strcpy(a->successor,target);
    strcpy(a->sponsor,sponsor_path);strcpy(a->sponsor_digest,sponsor_hash);strcpy(a->control,control);return 1;
}
static const char *recovery_body(const char *response) {
    const char *p=strstr(response,"\r\n\r\n");return p?p+4:response;
}
static int recovery_maintenance_matches(const RecoveryJson *j,int object,
                                        const char *generation,int ready) {
    return recovery_field(j,object,"protocol","KRONOS_MAINTENANCE_HANDOFF_V1") &&
        recovery_field(j,object,"generation",generation) &&
        recovery_field(j,object,"state",ready?"INACTIVE":"FAILED_ACTIVE") &&
        recovery_field(j,object,"active",ready?"false":"true") &&
        recovery_field(j,object,"startup",ready?"READY":"BLOCKED") &&
        recovery_field(j,object,"failure",ready?"null":"ACCEPTANCE_RESTORATION_NOT_ESTABLISHED");
}
static int recovery_worker_drainable(const RecoveryJson *j,int object,int owners,const char *kind) {
    long long workers=recovery_integer(j,object,"owned_workers"),queued=recovery_integer(j,object,"queued_items");
    if(workers<0 || queued<0 || !recovery_field(j,object,"continuity","COMPLETE") ||
       !recovery_field(j,object,"failure","null"))return 0;
    if(recovery_field(j,object,"state","IDLE"))return workers==0 && queued==0;
    /* The existing coordinator retains one owner ticket throughout each
     * worker's queue, callbacks and final writes. Zero is required by the
     * signed handoff, not by this pre-claim DRAINABLE check (ADR-0059). */
    return (recovery_field(j,object,"state","RUNNING") || recovery_field(j,object,"state","CANCELLATION_REQUESTED")) &&
        workers>0 && recovery_integer(j,object,"generation")>0 && recovery_integer(j,owners,kind)>=workers;
}
static int recovery_runtime_matches(const RecoveryAuthorization *a,const char *runtime,const char *status,const char *intraday) {
    RecoveryJson j,s,d;
    if(!recovery_json_document(&j,recovery_body(runtime)) || !recovery_json_document(&s,recovery_body(status)) ||
       !recovery_json_document(&d,recovery_body(intraday)))return 0;
    int process=recovery_json_get(&j,0,"process"),m=recovery_json_get(&j,0,"maintenance"),
        drain=recovery_json_get(&j,0,"maintenance_drain"),provider=recovery_json_get(&j,0,"provider_runtime"),
        monitor=recovery_json_get(&j,0,"monitoring"),shadow=recovery_json_get(&d,0,"live_shadow");
    if(!recovery_field(&j,0,"schema","KRONOS-RUNTIME-STATE/1.0.0") || recovery_integer(&j,process,"pid")!=a->pid ||
       !recovery_field(&j,process,"revision",a->predecessor) || !recovery_field(&j,process,"source_state","CLEAN_COMMIT") ||
       !recovery_maintenance_matches(&j,m,a->maintenance,0) ||
       !recovery_maintenance_matches(&s,recovery_json_get(&s,0,"maintenance"),a->maintenance,0) ||
       !recovery_field(&s,0,"service","KRONOS_BROWSER_V1") ||
       !recovery_field(&j,drain,"state","OPEN") || !recovery_field(&j,drain,"generation","null") || !recovery_field(&j,drain,"failure","null") ||
       !recovery_field(&j,0,"maintenance_claim","DRAINABLE") || !recovery_field(&s,0,"runtime_ready","false") ||
       !recovery_field(&s,0,"provider","DISCONNECTED") ||
       !recovery_field(&j,0,"rest_authentication","DISCONNECTED") || !recovery_field(&j,0,"rest_capability","ABSENT") ||
       !recovery_field(&j,0,"connection_attempt","null") ||
       !recovery_field(&j,provider,"cleanup_state","COMPLETE") || recovery_integer(&j,provider,"owned_work_count")!=0 ||
       recovery_integer(&j,provider,"retained_lease_count")!=0 || recovery_integer(&j,provider,"unresolved_cleanup_count")!=0 ||
       !recovery_field(&d,0,"active_operation_identity","null") || !recovery_field(&d,0,"current_failure","null") ||
       !recovery_field(&d,shadow,"failure","SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE") ||
       !recovery_field(&d,shadow,"runtime_accepted","false") || !recovery_field(&d,shadow,"epoch_failure","null") ||
       !recovery_field(&d,shadow,"publication_hook_failure","null"))return 0;
    int owners=recovery_json_get(&j,drain,"owners");if(owners<0 || j.token[owners].kind!='{')return 0;
    static const char *allowed[]={"SERVER_PULSE","HOUSEKEEPING","WO11","WO17","MONITORING_CALLBACK","NOTIFICATION","REMINDER","PROGRESSION","WO08_SHADOW"};
    for(int k=owners+1;k<j.token[owners].next;k=j.token[j.token[k].next].next){int known=0;
        for(size_t n=0;n<sizeof(allowed)/sizeof(allowed[0]);n++)if(recovery_json_equal(&j,k,allowed[n]))known=1;
        char name[64];int len=j.token[k].end-j.token[k].start;if(len<1 || len>=64)return 0;
        memcpy(name,j.text+j.token[k].start,(size_t)len);name[len]=0;
        if(!known || recovery_integer(&j,owners,name)<1)return 0;}
    for(int n=0;n<2;n++){int obj=recovery_json_get(&j,0,n?"intraday_wo17_work":"intraday_wo11_work");
        if(!recovery_worker_drainable(&j,obj,owners,n?"WO17":"WO11"))return 0;}
    for(int n=0;n<2;n++){int obj=recovery_json_get(&j,0,n?"analysis_execution":"analysis_work");
        if(!recovery_field(&j,obj,"state","IDLE") || recovery_integer(&j,obj,n?"owned_workers":"owned_work_count")!=0 ||
           recovery_integer(&j,obj,"queued_jobs")!=0)return 0;
        if(n && (!recovery_field(&j,obj,"cleanup_state","COMPLETE") || !recovery_field(&j,obj,"failure","null") ||
                  !recovery_field(&j,obj,"pid","null")))return 0;}
    static const char *zero[]={"session_count","active_session_count","owner_count","subscription_count"};
    for(size_t n=0;n<sizeof(zero)/sizeof(zero[0]);n++)if(recovery_integer(&j,monitor,zero[n])!=0)return 0;
    if(!recovery_field(&j,recovery_json_get(&j,monitor,"transport_cleanup"),"state","COMPLETE"))return 0;
    int house=recovery_json_get(&j,0,"housekeeping"),bulk=recovery_json_get(&j,0,"swing_bulk_import");
    long long house_workers=recovery_integer(&j,house,"owned_workers");
    int house_idle=recovery_field(&j,house,"lifecycle_state","IDLE") && house_workers==0 && recovery_field(&j,house,"pass_active","false");
    int house_counted=(recovery_field(&j,house,"lifecycle_state","RUNNING") || recovery_field(&j,house,"lifecycle_state","SCHEDULED")) &&
        house_workers>0 && recovery_integer(&j,house,"worker_generation")>0 &&
        recovery_integer(&j,owners,"HOUSEKEEPING")>=house_workers &&
        (recovery_field(&j,house,"pass_active","false") || recovery_field(&j,house,"pass_active","true"));
    return (house_idle || house_counted) && recovery_field(&j,house,"last_failure","null") &&
        recovery_field(&j,house,"shutdown_requested","false") && recovery_field(&j,bulk,"state","IDLE") &&
        recovery_field(&j,bulk,"batch_active","false");
}
static int recovery_run_helper(const char *repository,const char *executable,char *const arguments[],
                               const char *input,char *output,size_t capacity,int expected_exit);
static int recovery_package_identity(const char *repository,const char *python,const char *bundle,char out[65]) {
    char raw[67];
    char *arguments[]={(char*)python,"-B","-c","import sys; from tools.macos.package_launcher import verify; print(verify(sys.argv[1]))",(char*)bundle,NULL};
    if(!recovery_run_helper(repository,python,arguments,NULL,raw,sizeof(raw),0) || strlen(raw)!=65 || raw[64]!='\n')return 0;
    memcpy(out,raw,64);out[64]=0;return valid_token(out);
}
static int recovery_listener_record(const char *raw,pid_t pid) {
    /* lsof emits one process record and one mandatory file-descriptor record. */
    char prefix[48];snprintf(prefix,sizeof(prefix),"p%ld\nf",(long)pid);
    size_t n=strlen(prefix);if(strncmp(raw,prefix,n))return 0;
    const char *p=raw+n,*start=p;
    while(*p>='0' && *p<='9')p++;
    return p!=start && !strcmp(p,"\nn127.0.0.1:8947\n");
}
static int recovery_listener_scan(pid_t pid,int absent) {
    char raw[256];char *arguments[]={"lsof","-nP","-Fpfn","-iTCP:8947","-sTCP:LISTEN",NULL};
    return recovery_run_helper(NULL,"/usr/sbin/lsof",arguments,NULL,raw,sizeof(raw),absent?1:0) &&
        (absent ? raw[0]==0 : recovery_listener_record(raw,pid));
}
static int recovery_listener_owner(pid_t pid) { return recovery_listener_scan(pid,0); }
static int recovery_attempt_record(const RecoveryAuthorization *a,const char *generation,
                                   long long now,char *record,size_t capacity) {
    return snprintf(record,capacity,"{\"schema\":\"KRONOS-FAILED-ACTIVE-RECOVERY-ATTEMPT/1.0.0\",\"attempt\":\"%s\",\"authorization_sha256\":\"%s\",\"generation\":\"%s\",\"predecessor_pid\":%ld,\"predecessor_revision\":\"%s\",\"successor_revision\":\"%s\",\"reserved_at_us\":%lld}\n",a->attempt,a->digest,generation,(long)a->pid,a->predecessor,a->successor,now);
}
static int recovery_attempt_matches(const RecoveryAuthorization *a,const char *generation) {
    char path[PATH_MAX],record[1024],retained[1024];
    int n=recovery_attempt_record(a,generation,a->reserved_at,record,sizeof(record));
    return valid_token(generation) && a->reserved_at>=a->valid_from && a->reserved_at<a->valid_until &&
        n>0 && n<(int)sizeof(record) &&
        snprintf(path,sizeof(path),"%s/%s.attempt.json",a->root,a->attempt)<(int)sizeof(path) &&
        recovery_read_file(path,retained,sizeof(retained),1) && !strcmp(record,retained);
}
static int recovery_reserve(RecoveryAuthorization *a,const char *generation,long long now) {
    if(!valid_token(generation) || now<a->valid_from || now>=a->valid_until ||
       now<RECOVERY_START_US || now>=RECOVERY_END_US || !recovery_safe_path(a->root,1,1))return 0;
    char actual[65],path[PATH_MAX],record[1024];
    if(!recovery_file_digest(a->file,actual,1) || strcmp(actual,a->digest) ||
       snprintf(path,sizeof(path),"%s/%s.attempt.json",a->root,a->attempt)>=(int)sizeof(path))return 0;
    int n=recovery_attempt_record(a,generation,now,record,sizeof(record));
    if(n<1 || n>=(int)sizeof(record))return 0;
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(fd<0)return 0;
    size_t used=0;int ok=1;while(used<(size_t)n){ssize_t written=write(fd,record+used,(size_t)n-used);
        if(written<0&&errno==EINTR)continue;if(written<=0){ok=0;break;}used+=(size_t)written;}
    if(fsync(fd)!=0)ok=0;if(close(fd)!=0)ok=0;
    int directory=open(a->root,O_RDONLY|O_NOFOLLOW);if(directory<0)return 0;
    if(fsync(directory)!=0)ok=0;close(directory);
    /* Never remove or reuse a partial reservation, even when sync/readback failed. */
    a->reserved_at=now;
    return ok && recovery_attempt_matches(a,generation);
}
static int recovery_bindings_match(const RecoveryAuthorization *a,const char *repository,
                                  const char *python,const char *control_proof) {
    long long now=recovery_now_us();char actual[65];
    if(now<a->valid_from || now>=a->valid_until || now<RECOVERY_START_US || now>=RECOVERY_END_US ||
       !recovery_file_digest(a->file,actual,1) || strcmp(actual,a->digest) ||
       !recovery_file_digest(a->sponsor,actual,0) || strcmp(actual,a->sponsor_digest) ||
       !recovery_file_digest(a->relation,actual,0) || strcmp(actual,RECOVERY_RELATION) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,RECOVERY_DIAGNOSIS) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_package_identity(repository,python,canonical_bundle,actual) || strcmp(actual,a->package) ||
       !recovery_package_identity(repository,python,a->rollback,actual) || strcmp(actual,a->rollback_identity) ||
       !qualify_source(repository,python) || !repository_revision_matches(repository,a->successor))return 0;
    if(control_proof){
        pid_t pid=0;char proof[65]={0};
        int ok=recovery_file_digest(a->control,actual,1) && !strcmp(actual,a->control_digest) &&
            recovery_control_record(a->control,&pid,proof) && pid==a->pid && !strcmp(proof,control_proof) &&
            recovery_file_digest(a->control,actual,1) && !strcmp(actual,a->control_digest);
        memset(proof,0,sizeof(proof));if(!ok)return 0;
    }
    now=recovery_now_us();
    return now>=a->valid_from && now<a->valid_until && now>=RECOVERY_START_US && now<RECOVERY_END_US;
}
static int recovery_assess(const RecoveryAuthorization *a) {
    char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
    return read_backend_route("/runtime/status",runtime) && read_backend_route("/status",status) &&
        read_backend_route("/control/intraday-discovery/v2/status",intraday) &&
        recovery_runtime_matches(a,runtime,status,intraday) && recovery_listener_owner(a->pid);
}

/* Helpers have no runtime authority; they only validate existing durable bytes
 * or documents fetched by this launcher. All paths are explicit arguments. */
static int recovery_run_helper(const char *repository,const char *executable,char *const arguments[],
                               const char *input,char *output,size_t capacity,int expected_exit) {
    struct timespec deadline;
    if(clock_gettime(CLOCK_MONOTONIC,&deadline)!=0 || capacity<2)return 0;
    deadline.tv_sec+=BACKEND_START_READY_TIMEOUT_SECONDS;
    if(recovery_io_deadline)deadline=*recovery_io_deadline;
    int in[2],out[2];if(pipe(in)!=0)return 0;
    if(pipe(out)!=0){close(in[0]);close(in[1]);return 0;}
    pid_t child=fork();
    if(child<0){close(in[0]);close(in[1]);close(out[0]);close(out[1]);return 0;}
    if(child==0){
        char python_path[PATH_MAX*2];
        if(repository && (snprintf(python_path,sizeof(python_path),"%s/src:%s",repository,repository)>=(int)sizeof(python_path) ||
           chdir(repository)!=0 || setenv("PYTHONPATH",python_path,1)!=0))_exit(2);
        if(dup2(in[0],STDIN_FILENO)<0 || dup2(out[1],STDOUT_FILENO)<0 || dup2(out[1],STDERR_FILENO)<0)_exit(2);
        close(in[0]);close(in[1]);close(out[0]);close(out[1]);
        execv(executable,arguments);_exit(2);
    }
    close(in[0]);close(out[1]);
    struct sigaction ignore={0},previous={0};ignore.sa_handler=SIG_IGN;sigemptyset(&ignore.sa_mask);
    int installed=sigaction(SIGPIPE,&ignore,&previous)==0;
    int ok=installed && fcntl(in[1],F_SETFL,O_NONBLOCK)==0 && fcntl(out[0],F_SETFL,O_NONBLOCK)==0;
    size_t written=0,length=input?strlen(input):0;
    while(ok && written<length){
        if(!recovery_wait_io(in[1],POLLOUT,&deadline)){ok=0;break;}
        ssize_t n=write(in[1],input+written,length-written);
        if(n<0&&(errno==EINTR||errno==EAGAIN))continue;if(n<=0){ok=0;break;}written+=(size_t)n;}
    close(in[1]);if(installed && sigaction(SIGPIPE,&previous,NULL)!=0)ok=0;
    size_t used=0;
    int closed=0;
    while(ok){
        if(!recovery_wait_io(out[0],POLLIN,&deadline)){ok=0;break;}
        char extra;ssize_t n=used+1<capacity?read(out[0],output+used,capacity-1-used):read(out[0],&extra,1);
        if(n<0&&(errno==EINTR||errno==EAGAIN))continue;
        if(n<0){ok=0;break;}if(n==0){closed=1;break;}
        if(used+1>=capacity){ok=0;break;}used+=(size_t)n;
    }
    close(out[0]);if(memchr(output,0,used))ok=0;output[used]=0;
    int status=0;
    for(;;){
        pid_t result=waitpid(child,&status,WNOHANG);
        if(result==child)break;
        if(result<0&&errno!=EINTR)return 0;
        struct timespec now;if(!ok || clock_gettime(CLOCK_MONOTONIC,&now)!=0 || time_reached(&now,&deadline))return 0;
        struct timespec pause=time_until(&now,&deadline);nanosleep(&pause,NULL);
    }
    return ok && closed && WIFEXITED(status) && WEXITSTATUS(status)==expected_exit;
}
static int recovery_continuity(const char *repository,const char *python,const char *home,const char *generation) {
    char evidence[PATH_MAX],output[160],path[PATH_MAX],raw[8192],state[32],digest[65],count[32];
    if(snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",home)>=(int)sizeof(evidence))return 0;
    char *arguments[]={(char*)python,"-B","tools/failed_active_continuity.py","--evidence-root",evidence,
        NULL,NULL,NULL,NULL,NULL,NULL,NULL};
    if(generation){
        RecoveryJson j;
        if(!valid_token(generation) || snprintf(path,sizeof(path),"%s/Library/Application Support/KRONOS/runtime/maintenance/%s.json",home,generation)>=(int)sizeof(path) ||
           !recovery_read_file(path,raw,sizeof(raw),1) || !recovery_json_document(&j,raw))return 0;
        int record=recovery_json_get(&j,0,"record"),drain=recovery_json_get(&j,record,"drain"),
            checkpoint=recovery_json_get(&j,drain,"notification_checkpoint");
        long long pending=recovery_integer(&j,checkpoint,"pending_count");
        if(!recovery_field(&j,record,"generation",generation) || pending<0 ||
           !recovery_string(&j,checkpoint,"state",state,sizeof(state)) ||
           !recovery_string(&j,checkpoint,"sha256",digest,sizeof(digest)) || !valid_token(digest))return 0;
        snprintf(count,sizeof(count),"%lld",pending);
        arguments[5]="--checkpoint-state";arguments[6]=state;
        arguments[7]="--checkpoint-count";arguments[8]=count;
        arguments[9]="--checkpoint-sha256";arguments[10]=digest;
    }
    if(!recovery_run_helper(repository,python,arguments,NULL,output,sizeof(output),0))return 0;
    const char *prefix="KRONOS_CONTINUITY_V1 VALID ";size_t n=strlen(prefix);
    if(strncmp(output,prefix,n) || strlen(output)!=n+65 || output[n+64]!='\n')return 0;
    output[n+64]=0;return valid_token(output+n);
}
typedef struct RecoverySuccessorContext {
    const RecoveryAuthorization *authority;
    const char *repository,*python,*generation,*home;
    pid_t child;
    struct timespec deadline;
} RecoverySuccessorContext;
static RecoverySuccessorContext recovery_successor={0};

static int recovery_successor_ready(void) {
    const RecoveryAuthorization *a=recovery_successor.authority;
    char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
    pid_t controlled_pid=0;char proof[65]={0};
    if(!a || !recovery_control_record(a->control,&controlled_pid,proof))return 0;
    memset(proof,0,sizeof(proof));
    if(controlled_pid!=recovery_successor.child || !recovery_listener_owner(controlled_pid) ||
       !read_backend_route("/runtime/status",runtime) || !read_backend_route("/status",status) ||
       !read_backend_route("/control/intraday-discovery/v2/status",intraday))return 0;
    char input[BACKEND_STATUS_RESPONSE_BYTES*3],output[100],pid[32],parent[32],from[32],until[32],maintenance[PATH_MAX],evidence[PATH_MAX];
    if(snprintf(input,sizeof(input),"[%s,%s,%s]",recovery_body(runtime),recovery_body(status),recovery_body(intraday))>=(int)sizeof(input) ||
       snprintf(maintenance,sizeof(maintenance),"%s/Library/Application Support/KRONOS/runtime/maintenance",recovery_successor.home)>=(int)sizeof(maintenance) ||
       snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",recovery_successor.home)>=(int)sizeof(evidence))return 0;
    snprintf(pid,sizeof(pid),"%ld",(long)controlled_pid);snprintf(parent,sizeof(parent),"%ld",(long)a->pid);
    snprintf(from,sizeof(from),"%lld",a->valid_from);snprintf(until,sizeof(until),"%lld",a->valid_until);
    char *arguments[]={(char*)recovery_successor.python,"-B","tools/failed_active_successor.py",
        "--relation",(char*)a->relation,"--relation-sha256",RECOVERY_RELATION,
        "--capability",RECOVERY_CAPABILITY,"--pid",pid,"--parent-pid",parent,
        "--revision",(char*)a->successor,"--generation",(char*)recovery_successor.generation,
        "--maintenance-root",maintenance,"--evidence-root",evidence,"--valid-from-us",from,"--valid-until-us",until,NULL};
    int valid=recovery_run_helper(recovery_successor.repository,recovery_successor.python,arguments,input,output,sizeof(output),0) &&
        !strcmp(output,"KRONOS_RECOVERY_SUCCESSOR_V1 VALID\n") &&
        recovery_attempt_matches(a,recovery_successor.generation) &&
        recovery_listener_owner(controlled_pid) &&
        recovery_now_us()>=a->valid_from && recovery_now_us()<a->valid_until && recovery_now_us()<RECOVERY_END_US;
    struct timespec now;
    return valid && monotonic_now(&now)==0 && !time_reached(&now,&recovery_successor.deadline);
}

static BackendStartResult start_backend(
    const char *repository,
    const char *python,
    const char *browser_entry,
    const char *python_path,
    pid_t previous_pid,
    const char *previous_token,
    const char *generation,
    const char *previous_revision
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
            if (previous_revision != NULL && previous_revision[0] != '\0') {
                if (setenv("KRONOS_MAINTENANCE_PROTOCOL", "V2", 1) != 0 ||
                    setenv("KRONOS_MAINTENANCE_REVISION", previous_revision, 1) != 0) _exit(1);
            } else if (unsetenv("KRONOS_MAINTENANCE_PROTOCOL") != 0 ||
                       unsetenv("KRONOS_MAINTENANCE_REVISION") != 0) _exit(1);
        } else {
            (void)unsetenv("KRONOS_MAINTENANCE_GENERATION");
            (void)unsetenv("KRONOS_MAINTENANCE_PARENT");
            (void)unsetenv("KRONOS_MAINTENANCE_PROOF");
            (void)unsetenv("KRONOS_MAINTENANCE_PROTOCOL");
            (void)unsetenv("KRONOS_MAINTENANCE_REVISION");
        }
        const char *launch_mode = getenv("KRONOS_LAUNCH_MODE");
        if (
            launch_mode != NULL && (strcmp(launch_mode, "GOVERNED_REPLACEMENT") == 0 || strcmp(launch_mode, RECOVERY_CLASS) == 0) &&
            (unsetenv("KRONOS_LAUNCH_MODE") != 0 ||
             unsetenv("KRONOS_REPLACEMENT_REVISION") != 0 || unsetenv("KRONOS_RECOVERY_ATTEMPT") != 0)
        ) _exit(1);
        execl(python, python, "-B", browser_entry, "--no-browser", (char *)NULL);
        _exit(1);
    }
    BackendStartMonitor monitor=production_backend_start_monitor;
    if(recovery_successor.authority){
        recovery_successor.child=child;monitor.ready=recovery_successor_ready;
        if(monotonic_now(&recovery_successor.deadline)!=0)return BACKEND_START_INTERNAL_FAILURE;
        recovery_successor.deadline.tv_sec+=BACKEND_START_READY_TIMEOUT_SECONDS;
        recovery_io_deadline=&recovery_successor.deadline;
    }
    BackendStartResult result=monitor_backend_start(
        child,
        BACKEND_START_READY_TIMEOUT_SECONDS,
        &monitor
    );
    recovery_io_deadline=NULL;
    return result;
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
    int recovery = mode != NULL && strcmp(mode, RECOVERY_CLASS) == 0;
    const char *recovery_attempt = getenv("KRONOS_RECOVERY_ATTEMPT");
    const char *target_revision = getenv("KRONOS_REPLACEMENT_REVISION");
    const char *migration = getenv("KRONOS_LEGACY_BOOTSTRAP_ID");
    const char *migration_proof = getenv("KRONOS_LEGACY_BOOTSTRAP_PROOF");
    if ((mode != NULL && !bootstrap && !replacement && !recovery) ||
        (!bootstrap && (migration != NULL || migration_proof != NULL))) return 1;
    if (bootstrap && (migration == NULL || migration_proof == NULL ||
        strlen(migration) != 64 || strlen(migration_proof) != 64 ||
        strspn(migration, "0123456789abcdef") != 64 ||
        strspn(migration_proof, "0123456789abcdef") != 64 ||
        getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
        getenv("KRONOS_MAINTENANCE_PARENT") != NULL ||
        getenv("KRONOS_MAINTENANCE_PROOF") != NULL ||
        getenv("KRONOS_MAINTENANCE_PROTOCOL") != NULL ||
        getenv("KRONOS_MAINTENANCE_REVISION") != NULL)) return 1;
    if (
        (replacement && (
            !valid_revision(target_revision) ||
            migration != NULL || migration_proof != NULL ||
            getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
            getenv("KRONOS_MAINTENANCE_PARENT") != NULL ||
            getenv("KRONOS_MAINTENANCE_PROOF") != NULL
            || getenv("KRONOS_MAINTENANCE_PROTOCOL") != NULL
            || getenv("KRONOS_MAINTENANCE_REVISION") != NULL
        )) ||
        (!replacement && !recovery && target_revision != NULL) ||
        (recovery && (!valid_token(recovery_attempt) || !valid_revision(target_revision) || bootstrap ||
            migration != NULL || migration_proof != NULL || getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
            getenv("KRONOS_MAINTENANCE_PARENT") != NULL || getenv("KRONOS_MAINTENANCE_PROOF") != NULL ||
            getenv("KRONOS_MAINTENANCE_PROTOCOL") != NULL || getenv("KRONOS_MAINTENANCE_REVISION") != NULL)) ||
        (!recovery && recovery_attempt != NULL)
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
    if ((replacement || recovery) && !repository_revision_matches(repository, target_revision)) {
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
    if (!bootstrap && !replacement && !recovery && backend_is_reusable(control_path)) return open_workspace();

    pid_t backend_pid = 0;
    ReplacementReadiness readiness = REPLACEMENT_NOT_READY;
    char token[65] = {0};
    RecoveryAuthorization recovery_authority;
    if (recovery) {
        char root[PATH_MAX],installed[65],rollback[65],relation[PATH_MAX];
        if (snprintf(root,sizeof(root),"%s/Library/Application Support/KRONOS/runtime/failed-active-recovery-v1",home)>=(int)sizeof(root) ||
            !recovery_control_record(control_path,&backend_pid,token) ||
            !recovery_load_authorization(root,recovery_attempt,control_path,backend_pid,target_revision,recovery_now_us(),&recovery_authority) ||
            snprintf(relation,sizeof(relation),"%s/Library/Application Support/KRONOS/evidence/intraday-v1/live-shadow-v1/epochs-v1/WO06H-SUCCESSOR_COMPATIBILITY-4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef.json",home)>=(int)sizeof(relation) ||
            strcmp(recovery_authority.relation,relation) ||
            !recovery_package_identity(repository,python,canonical_bundle,installed) || strcmp(installed,recovery_authority.package) ||
            !recovery_package_identity(repository,python,recovery_authority.rollback,rollback) || strcmp(rollback,recovery_authority.rollback_identity) ||
            !recovery_assess(&recovery_authority)) { memset(token,0,sizeof(token));return show_restart_blocked(); }
    }
    if (replacement) {
        if (!read_control_record(control_path, &backend_pid, token)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        readiness = backend_replacement_readiness(
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
    char predecessor_revision[41] = {0};
    if (recovery) strcpy(predecessor_revision,recovery_authority.predecessor);
    if (replacement && readiness == REPLACEMENT_REQUIRED) {
        char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
        if (!read_backend_route("/runtime/status", response) ||
            !runtime_process_revision(response, backend_pid, predecessor_revision) ||
            strcmp(predecessor_revision, target_revision) == 0 ||
            !new_runtime_is_drainable(response)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
    }
    unsigned char random_bytes[32];
    arc4random_buf(random_bytes, sizeof(random_bytes));
    for (size_t i = 0; i < sizeof(random_bytes); ++i)
        (void)snprintf(generation + i * 2, 3, "%02x", random_bytes[i]);
    int socket_connected = connect_backend();
    if (socket_connected >= 0) {
        (void)close(socket_connected);
        if (!bootstrap && !replacement && !recovery) return show_existing_backend_unhealthy();
        if (replacement && readiness == REPLACEMENT_REQUIRED_OLD_CF55) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        if (
            (!replacement && !recovery && !read_control_record(control_path, &backend_pid, token)) ||
            (recovery && (!recovery_continuity(repository,python,home,NULL) ||
                !recovery_assess(&recovery_authority) ||
                !recovery_bindings_match(&recovery_authority,repository,python,token) ||
                !recovery_reserve(&recovery_authority,generation,recovery_now_us()))) ||
            !request_graceful_shutdown(backend_pid, token, generation, replacement || recovery) ||
            !wait_for_backend_stop(backend_pid)
        ) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        if ((replacement || recovery) && !verify_v2_handoff(repository, python, python_path,
                control_path, generation, backend_pid, predecessor_revision, token)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
    } else if (replacement || recovery) {
        (void)memset(token, 0, sizeof(token));
        return show_restart_blocked();
    } else if (!bootstrap && !recovery && !cold_start_has_no_control_or_live_handoff(control_path)) {
        return show_existing_backend_unhealthy();
    }

    if (recovery) {
        if (!recovery_continuity(repository,python,home,generation) ||
            !recovery_bindings_match(&recovery_authority,repository,python,NULL) ||
            !recovery_attempt_matches(&recovery_authority,generation) ||
            !verify_v2_handoff(repository,python,python_path,control_path,generation,backend_pid,predecessor_revision,token) ||
            kill(backend_pid,0)==0 || errno!=ESRCH) {
            memset(token,0,sizeof(token));return show_restart_blocked();
        }
        if(!recovery_listener_scan(0,1)){memset(token,0,sizeof(token));return show_restart_blocked();}
        long long final_now=recovery_now_us();
        if(final_now<recovery_authority.valid_from || final_now>=recovery_authority.valid_until || final_now>=RECOVERY_END_US){
            memset(token,0,sizeof(token));return show_restart_blocked();}
        recovery_successor=(RecoverySuccessorContext){.authority=&recovery_authority,
            .repository=repository,.python=python,.generation=generation,.home=home};
    }
    BackendStartResult start_result = start_backend(
        repository,
        python,
        browser_entry,
        python_path,
        backend_pid,
        token,
        generation,
        predecessor_revision
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
