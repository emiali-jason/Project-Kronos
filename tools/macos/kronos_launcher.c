#include <arpa/inet.h>
#include <CommonCrypto/CommonDigest.h>
#include <CommonCrypto/CommonHMAC.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <libproc.h>
#include <mach-o/dyld.h>
#include <netinet/in.h>
#include <poll.h>
#include <pwd.h>
#include <sys/event.h>
#include <sys/sysctl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
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
#define RECOVERY_HISTORY_SCHEMA "KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/2.0.0"
#define RECOVERY_HISTORY_PREDECESSOR "37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3"
#define RECOVERY_HISTORY_CAPABILITY "WO06H-CAPABILITY-f61cfe6c7395d0ee8554d82946a5a7fa88444c09151f53bc171253a3d35aa31b"
#define RECOVERY_HISTORY_RELATION "c718842b6927ee058b4fd135df6eaa57873ffc0b901c597372110bb46338b0f8"
#define RECOVERY_HISTORY_DIAGNOSIS "c6bb42f497b6e1a2acb056ccc9fd09b2476b73a2e182526fb2bc240e72298d08"
#define RECOVERY_HISTORY_MAX_VALIDITY_US 1800000000LL
/* Closed IWO-07R3 predecessor pins; not generic FAILED_ACTIVE authority. */
#define RECOVERY_SWING_SCHEMA "KRONOS-IWO07R3-RECOVERY-AUTHORIZATION/1.0.0"
#define RECOVERY_SWING_PREDECESSOR "7b0729402687b2f05607ce99a5c99a9cea35568b"
#define RECOVERY_SWING_PID 45583
#define RECOVERY_SWING_START_US 1791996740356956LL
#define RECOVERY_SWING_GENERATION "02a8392f4d88082bf96d3e807c6f1acf00e381ac63f62f7433aecfd2e1c762b3"
#define RECOVERY_SWING_PACKAGE "35a468ca66dfe127479112d777323a63c1221cd381c63d93db09a8b36d4cbd18"
#define RECOVERY_SWING_DIAGNOSIS "014e7571a779a6411655240b92dfbe77bda4f85661c95c243738118b1e3d4d6b"
/* Closed October release-recovery engineering extension. Independent exact-
 * artifact approval and Sponsor release authority remain separate gates. */
#define RECOVERY_RELEASE_SCHEMA "KRONOS-SWING-RELEASE-RECOVERY-AUTHORIZATION/1.0.0"
#define RECOVERY_RELEASE_INCIDENT "KRONOS-SWING-FAILED-ACTIVE-AND-FENCED-RECOVERY-ENGINEERING-20261022"
#define RECOVERY_RELEASE_PREDECESSOR "355922f92f7b826191ae86bd7bb0473349f3c1cc"
#define RECOVERY_RELEASE_ROLLBACK "1579f1cbad2f98370b62f5511a7d339c131ab15a"
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
    long long valid_from,valid_until,reserved_at;pid_t pid;int historical, swing_incident;char artifact_receipt_digest[65];
    int swing_release;long long predecessor_start_us;
    char capability[84],startup_failure[80],diagnosis_digest[65];
} RecoveryAuthorization;

static int recovery_time_valid(const RecoveryAuthorization *a,long long now) {
    if(now<a->valid_from || now>=a->valid_until)return 0;
    return (a->historical || a->swing_incident || a->swing_release) ? (a->valid_from>=RECOVERY_END_US && now>=RECOVERY_END_US &&
        a->valid_until-a->valid_from<=RECOVERY_HISTORY_MAX_VALIDITY_US) :
        (a->valid_until<=RECOVERY_END_US && now>=RECOVERY_START_US && now<RECOVERY_END_US);
}
static const char *recovery_capability(const RecoveryAuthorization *a) {
    return a->swing_release?a->capability:(a->historical?RECOVERY_HISTORY_CAPABILITY:RECOVERY_CAPABILITY);
}
static const char *recovery_relation(const RecoveryAuthorization *a) {
    return (a->swing_incident || a->swing_release)?a->artifact_receipt_digest:(a->historical?RECOVERY_HISTORY_RELATION:RECOVERY_RELATION);
}
static const char *recovery_diagnosis(const RecoveryAuthorization *a) {
    return a->swing_release?a->diagnosis_digest:(a->swing_incident?RECOVERY_SWING_DIAGNOSIS:(a->historical?RECOVERY_HISTORY_DIAGNOSIS:RECOVERY_DIAGNOSIS));
}

static int recovery_swing_process_start(pid_t pid) {
    struct proc_bsdinfo info;
    return pid==RECOVERY_SWING_PID &&
        proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&info,sizeof(info))==(int)sizeof(info) &&
        (long long)info.pbi_start_tvsec*1000000+info.pbi_start_tvusec==RECOVERY_SWING_START_US;
}
static int recovery_swing_authorization(const RecoveryJson *j,const char *raw,const char *control,
                                       pid_t pid,const char *target,long long now,RecoveryAuthorization *a) {
    char reference[256],actual[65];
    a->swing_incident=1;
    if(j->token[0].count!=23 || pid!=RECOVERY_SWING_PID || !strcmp(target,RECOVERY_SWING_PREDECESSOR) ||
       !recovery_field(j,0,"recovery_class",RECOVERY_CLASS) || !recovery_field(j,0,"state","SPONSOR_APPROVED") ||
       !recovery_field(j,0,"attempt_identity",a->attempt) ||
       !recovery_field(j,0,"predecessor_revision",RECOVERY_SWING_PREDECESSOR) ||
       !recovery_field(j,0,"successor_revision",target) || recovery_integer(j,0,"predecessor_pid")!=pid ||
       recovery_integer(j,0,"predecessor_start_us")!=RECOVERY_SWING_START_US ||
       !recovery_field(j,0,"predecessor_maintenance_identity",RECOVERY_SWING_GENERATION) ||
       !recovery_field(j,0,"predecessor_package_identity",RECOVERY_SWING_PACKAGE) ||
       !recovery_field(j,0,"rollback_package_identity",RECOVERY_SWING_PACKAGE) ||
       !recovery_field(j,0,"diagnosis_sha256",RECOVERY_SWING_DIAGNOSIS) ||
       !recovery_string(j,0,"sponsor_authorization_reference",reference,sizeof(reference)) ||
       !recovery_string(j,0,"sponsor_authorization_path",a->sponsor,sizeof(a->sponsor)) ||
       !recovery_string(j,0,"sponsor_authorization_sha256",a->sponsor_digest,sizeof(a->sponsor_digest)) ||
       !valid_token(a->sponsor_digest) || !recovery_file_digest(a->sponsor,actual,0) || strcmp(actual,a->sponsor_digest) ||
       !recovery_string(j,0,"private_control_sha256",a->control_digest,sizeof(a->control_digest)) ||
       !recovery_file_digest(control,actual,1) || strcmp(actual,a->control_digest) ||
       !recovery_string(j,0,"installed_package_identity",a->package,sizeof(a->package)) ||
       !valid_token(a->package) || !strcmp(a->package,RECOVERY_SWING_PACKAGE) ||
       !recovery_string(j,0,"rollback_bundle",a->rollback,sizeof(a->rollback)) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_string(j,0,"stage_a_receipt_path",a->relation,sizeof(a->relation)) ||
       !recovery_string(j,0,"stage_a_receipt_sha256",a->artifact_receipt_digest,sizeof(a->artifact_receipt_digest)) ||
       !valid_token(a->artifact_receipt_digest) || !recovery_file_digest(a->relation,actual,1) ||
       strcmp(actual,a->artifact_receipt_digest) ||
       !recovery_string(j,0,"diagnosis_path",a->diagnosis,sizeof(a->diagnosis)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,RECOVERY_SWING_DIAGNOSIS) ||
       !recovery_file_digest(a->file,a->digest,1))return 0;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];char hex[65];
    CC_SHA256(raw,(CC_LONG)strlen(raw),digest);
    for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    a->valid_from=recovery_integer(j,0,"valid_from_us");a->valid_until=recovery_integer(j,0,"valid_until_us");
    if(strcmp(hex,a->digest) || a->valid_from<=RECOVERY_SWING_START_US ||
       a->valid_until<=a->valid_from || !recovery_time_valid(a,now))return 0;
    a->pid=pid;strcpy(a->predecessor,RECOVERY_SWING_PREDECESSOR);strcpy(a->successor,target);
    strcpy(a->maintenance,RECOVERY_SWING_GENERATION);strcpy(a->rollback_identity,RECOVERY_SWING_PACKAGE);
    strcpy(a->control,control);return 1;
}

static int recovery_release_failure(const char *failure) {
    static const char *allowed[]={"ACCEPTANCE_RESTORATION_NOT_ESTABLISHED",
        "SWING_RESTORATION_NOT_ESTABLISHED","RUNTIME_RESTORATION_PROOF_UNAVAILABLE",
        "WO11_RESTORATION_FAILED","WO17_RESTORATION_FAILED","STARTUP_COMPLETION_RECORD_UNAVAILABLE"};
    for(size_t n=0;n<sizeof(allowed)/sizeof(allowed[0]);n++)if(!strcmp(failure,allowed[n]))return 1;
    return 0;
}
static int recovery_release_process_start(const RecoveryAuthorization *a) {
    struct proc_bsdinfo info;
    return a->pid>1 && a->predecessor_start_us>0 &&
        proc_pidinfo(a->pid,PROC_PIDTBSDINFO,0,&info,sizeof(info))==(int)sizeof(info) &&
        (long long)info.pbi_start_tvsec*1000000+(long long)info.pbi_start_tvusec==a->predecessor_start_us;
}
static int recovery_release_authorization(const RecoveryJson *j,const char *raw,const char *control,
                                         pid_t pid,const char *target,long long now,RecoveryAuthorization *a) {
    char reference[256],actual[65];
    a->swing_release=1;
    if(j->token[0].count!=25 ||
       !recovery_field(j,0,"recovery_class",RECOVERY_CLASS) || !recovery_field(j,0,"state","SPONSOR_APPROVED") ||
       !recovery_field(j,0,"incident_id",RECOVERY_RELEASE_INCIDENT) || !recovery_field(j,0,"attempt_identity",a->attempt) ||
       !recovery_string(j,0,"predecessor_revision",a->predecessor,sizeof(a->predecessor)) ||
       (strcmp(a->predecessor,RECOVERY_RELEASE_PREDECESSOR) && strcmp(a->predecessor,RECOVERY_RELEASE_ROLLBACK)) ||
       !strcmp(target,a->predecessor) || !recovery_field(j,0,"successor_revision",target) ||
       recovery_integer(j,0,"predecessor_pid")!=pid ||
       !recovery_string(j,0,"predecessor_maintenance_identity",a->maintenance,sizeof(a->maintenance)) || !valid_token(a->maintenance) ||
       !recovery_string(j,0,"expected_startup_failure",a->startup_failure,sizeof(a->startup_failure)) ||
       !recovery_release_failure(a->startup_failure) ||
       !recovery_string(j,0,"expected_successor_capability",a->capability,sizeof(a->capability)) ||
       strncmp(a->capability,"WO06H-CAPABILITY-",17) || !valid_token(a->capability+17) ||
       !recovery_string(j,0,"sponsor_authorization_reference",reference,sizeof(reference)) ||
       !recovery_string(j,0,"sponsor_authorization_path",a->sponsor,sizeof(a->sponsor)) ||
       !recovery_string(j,0,"sponsor_authorization_sha256",a->sponsor_digest,sizeof(a->sponsor_digest)) ||
       !valid_token(a->sponsor_digest) || !recovery_file_digest(a->sponsor,actual,0) || strcmp(actual,a->sponsor_digest) ||
       !recovery_string(j,0,"private_control_sha256",a->control_digest,sizeof(a->control_digest)) ||
       !valid_token(a->control_digest) || !recovery_file_digest(control,actual,1) || strcmp(actual,a->control_digest) ||
       !recovery_string(j,0,"installed_package_identity",a->package,sizeof(a->package)) || !valid_token(a->package) ||
       !recovery_string(j,0,"rollback_bundle",a->rollback,sizeof(a->rollback)) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_string(j,0,"rollback_package_identity",a->rollback_identity,sizeof(a->rollback_identity)) || !valid_token(a->rollback_identity) ||
       !recovery_string(j,0,"artifact_review_path",a->relation,sizeof(a->relation)) ||
       !recovery_string(j,0,"artifact_review_sha256",a->artifact_receipt_digest,sizeof(a->artifact_receipt_digest)) ||
       !valid_token(a->artifact_receipt_digest) || !recovery_file_digest(a->relation,actual,1) || strcmp(actual,a->artifact_receipt_digest) ||
       !recovery_string(j,0,"diagnosis_path",a->diagnosis,sizeof(a->diagnosis)) ||
       !recovery_string(j,0,"diagnosis_sha256",a->diagnosis_digest,sizeof(a->diagnosis_digest)) ||
       !valid_token(a->diagnosis_digest) || !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,a->diagnosis_digest) ||
       !recovery_file_digest(a->file,a->digest,1))return 0;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];char hex[65];
    CC_SHA256(raw,(CC_LONG)strlen(raw),digest);
    for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    a->valid_from=recovery_integer(j,0,"valid_from_us");a->valid_until=recovery_integer(j,0,"valid_until_us");
    a->predecessor_start_us=recovery_integer(j,0,"predecessor_start_us");
    if(strcmp(hex,a->digest) || a->predecessor_start_us<=0 || a->valid_from<=a->predecessor_start_us ||
       a->valid_until<=a->valid_from || !recovery_time_valid(a,now))return 0;
    a->pid=pid;strcpy(a->successor,target);strcpy(a->control,control);return 1;
}

static int recovery_load_authorization(const char *root,const char *attempt,
                                      const char *control,pid_t pid,const char *target,
                                      long long now,RecoveryAuthorization *a) {
    if(!valid_token(attempt) || !valid_revision(target) || pid<2 ||
       !recovery_safe_path(root,1,1))return 0;
    memset(a,0,sizeof(*a));strcpy(a->root,root);strcpy(a->attempt,attempt);
    if(snprintf(a->file,sizeof(a->file),"%s/%s.authorization.json",root,attempt)>=(int)sizeof(a->file))return 0;
    char raw[16384],reference[256],sponsor_path[PATH_MAX],sponsor_hash[65],actual[65];RecoveryJson j;
    if(!recovery_read_file(a->file,raw,sizeof(raw),1) || !recovery_json_document(&j,raw))return 0;
    if(recovery_field(&j,0,"schema",RECOVERY_SWING_SCHEMA))
        return recovery_swing_authorization(&j,raw,control,pid,target,now,a);
    if(recovery_field(&j,0,"schema",RECOVERY_RELEASE_SCHEMA))
        return recovery_release_authorization(&j,raw,control,pid,target,now,a);
    a->historical=recovery_field(&j,0,"schema",RECOVERY_HISTORY_SCHEMA);
    if((a->historical ? (j.token[0].count!=25 ||
            !recovery_field(&j,0,"research_state","HISTORICAL_ACCEPTANCE_EXPIRED")) :
            (j.token[0].count!=24 || !recovery_field(&j,0,"schema",RECOVERY_SCHEMA))) ||
       !recovery_field(&j,0,"recovery_class",RECOVERY_CLASS) ||
       !recovery_field(&j,0,"state","SPONSOR_APPROVED") || !recovery_field(&j,0,"attempt_identity",attempt) ||
       !recovery_string(&j,0,"sponsor_authorization_reference",reference,sizeof(reference)) ||
       !recovery_string(&j,0,"sponsor_authorization_path",sponsor_path,sizeof(sponsor_path)) ||
       !recovery_string(&j,0,"sponsor_authorization_sha256",sponsor_hash,sizeof(sponsor_hash)) || !valid_token(sponsor_hash) ||
       !recovery_file_digest(sponsor_path,actual,0) || strcmp(actual,sponsor_hash) ||
       !recovery_field(&j,0,"predecessor_revision",a->historical?RECOVERY_HISTORY_PREDECESSOR:RECOVERY_PREDECESSOR) ||
       !recovery_field(&j,0,"successor_revision",target) ||
       !recovery_field(&j,0,"expected_successor_capability",recovery_capability(a)) ||
       !recovery_field(&j,0,"compatibility_relation_sha256",recovery_relation(a)) ||
       !recovery_field(&j,0,"diagnosis_sha256",recovery_diagnosis(a)) ||
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
       !recovery_file_digest(a->relation,actual,0) || strcmp(actual,recovery_relation(a)) ||
       !recovery_string(&j,0,"diagnosis_path",a->diagnosis,sizeof(a->diagnosis)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,recovery_diagnosis(a)) ||
       !recovery_file_digest(a->file,a->digest,1))return 0;
    unsigned char parsed_digest[CC_SHA256_DIGEST_LENGTH]; char parsed_hex[65];
    CC_SHA256(raw,(CC_LONG)strlen(raw),parsed_digest);
    for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)snprintf(parsed_hex+2*i,3,"%02x",parsed_digest[i]);
    if(strcmp(parsed_hex,a->digest))return 0;
    a->valid_from=recovery_integer(&j,0,"valid_from_us");a->valid_until=recovery_integer(&j,0,"valid_until_us");
    if(a->valid_from<0 || a->valid_until<=a->valid_from || !recovery_time_valid(a,now))return 0;
    a->pid=pid;strcpy(a->predecessor,a->historical?RECOVERY_HISTORY_PREDECESSOR:RECOVERY_PREDECESSOR);strcpy(a->successor,target);
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
static int recovery_incident_maintenance(const RecoveryAuthorization *a,const RecoveryJson *j,int object) {
    if(a->swing_release)return recovery_field(j,object,"protocol","KRONOS_MAINTENANCE_HANDOFF_V1") &&
        recovery_field(j,object,"generation",a->maintenance) && recovery_field(j,object,"state","FAILED_ACTIVE") &&
        recovery_field(j,object,"active","true") && recovery_field(j,object,"startup","BLOCKED") &&
        recovery_release_failure(a->startup_failure) && recovery_field(j,object,"failure",a->startup_failure);
    if(!a->swing_incident)return recovery_maintenance_matches(j,object,a->maintenance,0);
    return recovery_field(j,object,"protocol","KRONOS_MAINTENANCE_HANDOFF_V1") &&
        recovery_field(j,object,"generation",RECOVERY_SWING_GENERATION) &&
        recovery_field(j,object,"state","FAILED_ACTIVE") && recovery_field(j,object,"active","true") &&
        recovery_field(j,object,"startup","BLOCKED") &&
        recovery_field(j,object,"failure","SWING_RESTORATION_NOT_ESTABLISHED");
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
       !recovery_incident_maintenance(a,&j,m) ||
       !recovery_incident_maintenance(a,&s,recovery_json_get(&s,0,"maintenance")) ||
       !recovery_field(&s,0,"service","KRONOS_BROWSER_V1") ||
       !recovery_field(&j,drain,"state","OPEN") || !recovery_field(&j,drain,"generation","null") || !recovery_field(&j,drain,"failure","null") ||
       !recovery_field(&j,0,"maintenance_claim","DRAINABLE") || !recovery_field(&s,0,"runtime_ready","false") ||
       !recovery_field(&s,0,"provider","DISCONNECTED") ||
       !recovery_field(&j,0,"rest_authentication","DISCONNECTED") || !recovery_field(&j,0,"rest_capability","ABSENT") ||
       !recovery_field(&j,0,"connection_attempt","null") ||
       !recovery_field(&j,provider,"cleanup_state","COMPLETE") || recovery_integer(&j,provider,"owned_work_count")!=0 ||
       recovery_integer(&j,provider,"retained_lease_count")!=0 || recovery_integer(&j,provider,"unresolved_cleanup_count")!=0 ||
       !recovery_field(&d,0,"active_operation_identity","null") || !recovery_field(&d,0,"current_failure","null") ||
       !recovery_field(&d,shadow,"failure",(a->swing_incident || a->swing_release)?"null":(a->historical?"SHADOW_RESTORATION_WINDOW_NOT_ACTIVE":"SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE")) ||
       !recovery_field(&d,shadow,"runtime_accepted","false") || !recovery_field(&d,shadow,"epoch_failure","null") ||
       !recovery_field(&d,shadow,"publication_hook_failure","null"))return 0;
    if(a->swing_release){
        int window=recovery_json_get(&d,shadow,"window"),counts=recovery_json_get(&d,shadow,"counts");
        if(!recovery_field(&d,shadow,"acceptance_disposition","HISTORICAL_ACCEPTANCE_EXPIRED") ||
           !recovery_field(&d,shadow,"historical_restoration","KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0") ||
           !recovery_field(&d,shadow,"historical_evidence","READABLE") ||
           !recovery_field(&d,shadow,"collection_authority","EXPIRED") || !recovery_field(&d,shadow,"enabled","false") ||
           !recovery_field(&d,window,"start",RECOVERY_WINDOW_START) || !recovery_field(&d,window,"end",RECOVERY_WINDOW_END) ||
           recovery_integer(&d,counts,"cohort_a")!=1 || recovery_integer(&d,counts,"cohort_b")!=18 ||
           recovery_integer(&d,counts,"eod_available")!=0)return 0;
    }
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
static int recovery_swing_verify(const RecoveryAuthorization *a,const char *repository,const char *python,
                                 const char *phase,const char *documents,const char *generation,pid_t pid) {
    char output[100],process[32],maintenance[PATH_MAX],evidence[PATH_MAX];
    const char *home=getenv("HOME");if(!home)return 0;
    if(snprintf(maintenance,sizeof(maintenance),"%s/Library/Application Support/KRONOS/runtime/maintenance",home)>=(int)sizeof(maintenance) ||
       snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",home)>=(int)sizeof(evidence))return 0;
    snprintf(process,sizeof(process),"%ld",(long)pid);
    char *arguments[]={(char*)python,"-B","tools/failed_active_successor.py","--incident-phase",(char*)phase,
        "--authorization",(char*)a->file,"--authorization-sha256",(char*)a->digest,
        "--revision",(char*)a->successor,"--generation",(char*)generation,"--pid",process,
        "--maintenance-root",maintenance,"--evidence-root",evidence,NULL};
    return recovery_run_helper(repository,python,arguments,documents,output,sizeof(output),0) &&
        !strcmp(output,"KRONOS_IWO07R3_RECOVERY_V1 VALID\n");
}
static int recovery_release_verify(const RecoveryAuthorization *a,const char *repository,const char *python,
                                   const char *phase,const char *documents,const char *generation,pid_t pid) {
    char output[100],process[32],maintenance[PATH_MAX],evidence[PATH_MAX];
    const char *home=getenv("HOME");if(!home)return 0;
    if(snprintf(maintenance,sizeof(maintenance),"%s/Library/Application Support/KRONOS/runtime/maintenance",home)>=(int)sizeof(maintenance) ||
       snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",home)>=(int)sizeof(evidence))return 0;
    snprintf(process,sizeof(process),"%ld",(long)pid);
    char *arguments[]={(char*)python,"-B","tools/failed_active_successor.py","--release-phase",(char*)phase,
        "--authorization",(char*)a->file,"--authorization-sha256",(char*)a->digest,
        "--revision",(char*)a->successor,"--generation",(char*)generation,"--pid",process,
        "--maintenance-root",maintenance,"--evidence-root",evidence,NULL};
    return recovery_run_helper(repository,python,arguments,documents,output,sizeof(output),0) &&
        !strcmp(output,"KRONOS_SWING_RELEASE_RECOVERY_V1 VALID\n");
}
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
    if(!valid_token(generation) || !recovery_time_valid(a,now) || !recovery_safe_path(a->root,1,1))return 0;
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
    if(!recovery_time_valid(a,now) ||
       !recovery_file_digest(a->file,actual,1) || strcmp(actual,a->digest) ||
       !recovery_file_digest(a->sponsor,actual,0) || strcmp(actual,a->sponsor_digest) ||
       !recovery_file_digest(a->relation,actual,0) || strcmp(actual,recovery_relation(a)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,recovery_diagnosis(a)) ||
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
    if(a->swing_incident && ((!recovery_swing_verify(a,repository,python,"retired",NULL,a->maintenance,a->pid)) ||
        (control_proof && !recovery_swing_process_start(a->pid))))return 0;
    if(a->swing_release && ((!recovery_release_verify(a,repository,python,"retired",NULL,a->maintenance,a->pid)) ||
        (control_proof && !recovery_release_process_start(a))))return 0;
    now=recovery_now_us();
    return recovery_time_valid(a,now);
}
static int recovery_assess(const RecoveryAuthorization *a,const char *repository,const char *python) {
    char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
    if(!(read_backend_route("/runtime/status",runtime) && read_backend_route("/status",status) &&
        read_backend_route("/control/intraday-discovery/v2/status",intraday) &&
        recovery_runtime_matches(a,runtime,status,intraday) && recovery_listener_owner(a->pid)))return 0;
    if(!a->swing_incident && !a->swing_release)return 1;
    char input[BACKEND_STATUS_RESPONSE_BYTES*3];
    if(a->swing_release)return recovery_release_process_start(a) &&
        snprintf(input,sizeof(input),"[%s,%s,%s]",recovery_body(runtime),recovery_body(status),recovery_body(intraday))<(int)sizeof(input) &&
        recovery_release_verify(a,repository,python,"preflight",input,a->maintenance,a->pid);
    return recovery_swing_process_start(a->pid) &&
        snprintf(input,sizeof(input),"[%s,%s,%s]",recovery_body(runtime),recovery_body(status),recovery_body(intraday))<(int)sizeof(input) &&
        recovery_swing_verify(a,repository,python,"preflight",input,a->maintenance,a->pid);
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
        "--relation",(char*)a->relation,"--relation-sha256",(char*)recovery_relation(a),
        "--capability",(char*)recovery_capability(a),"--pid",pid,"--parent-pid",parent,
        "--revision",(char*)a->successor,"--generation",(char*)recovery_successor.generation,
        "--maintenance-root",maintenance,"--evidence-root",evidence,"--valid-from-us",from,"--valid-until-us",until,
        "--research-state",a->historical?"HISTORICAL_ACCEPTANCE_EXPIRED":"ACTIVE",NULL};
    int verified=a->swing_release ? recovery_release_verify(a,recovery_successor.repository,
        recovery_successor.python,"successor",input,recovery_successor.generation,controlled_pid) :
        a->swing_incident ? recovery_swing_verify(a,recovery_successor.repository,
        recovery_successor.python,"successor",input,recovery_successor.generation,controlled_pid) :
        (recovery_run_helper(recovery_successor.repository,recovery_successor.python,arguments,input,output,sizeof(output),0) &&
        !strcmp(output,"KRONOS_RECOVERY_SUCCESSOR_V1 VALID\n"));
    int valid=verified &&
        recovery_attempt_matches(a,recovery_successor.generation) &&
        recovery_listener_owner(controlled_pid) &&
        recovery_time_valid(a,recovery_now_us());
    struct timespec now;
    return valid && monotonic_now(&now)==0 && !time_reached(&now,&recovery_successor.deadline);
}

/* R3 native record issuance. Only this actual canonical controller owns L's
 * role-derived key. Qualified semantic helpers receive no token or MAC key. */
#define FFR3_PROTOCOL "KRONOS-FAILED-FENCED-RECOVERY-V1"
#define FFR3_VERSION "1.0.0"
#define FFR3_EXTERNAL "KRONOS-FAILED-FENCED-EXTERNAL-PROOF/1.0.0"
#define FFR3_MAX_RECORD (1024U*1024U)

typedef struct FFR3NativeCodec {
    unsigned char key[32];
    char key_id[65];
    char clock[16384];
    char controller[1024];
    pid_t predecessor;
} FFR3NativeCodec;

static size_t ffr3_token_start(const RecoveryJson *j,int token) {
    return (size_t)(j->token[token].start-(j->token[token].kind=='s'));
}
static size_t ffr3_token_end(const RecoveryJson *j,int token) {
    return (size_t)(j->token[token].end+(j->token[token].kind=='s'));
}
static int ffr3_canonical_token(const RecoveryJson *j,int token) {
    const RecoveryJsonToken *r=&j->token[token];
    if(r->kind=='s'){
        for(int p=r->start;p<r->end;p++){
            unsigned char c=(unsigned char)j->text[p];
            if(c<32 || c>126)return 0;
            if(c=='\\' && (++p>=r->end || (j->text[p]!='"' && j->text[p]!='\\')))return 0;
        }
        return 1;
    }
    if(r->kind=='v')return recovery_json_equal(j,token,"true") ||
        recovery_json_equal(j,token,"false") || recovery_json_equal(j,token,"null");
    if(r->kind!='{' && r->kind!='[')return 0;
    size_t cursor=(size_t)r->start+1;int last=-1;
    for(int child=token+1;child<r->next;){
        if(ffr3_token_start(j,child)!=cursor || !ffr3_canonical_token(j,child))return 0;
        if(r->kind=='{'){
            if(j->token[child].kind!='s')return 0;
            if(last>=0){
                size_t a=(size_t)(j->token[last].end-j->token[last].start);
                size_t b=(size_t)(j->token[child].end-j->token[child].start);
                int order=memcmp(j->text+j->token[last].start,j->text+j->token[child].start,a<b?a:b);
                if(order>0 || (order==0 && a>=b))return 0;
            }
            last=child;
            cursor=ffr3_token_end(j,child);
            if(j->text[cursor++]!=':')return 0;
            child=j->token[child].next;
            if(child>=r->next || ffr3_token_start(j,child)!=cursor || !ffr3_canonical_token(j,child))return 0;
        }
        cursor=ffr3_token_end(j,child);child=j->token[child].next;
        if(child<r->next && j->text[cursor++]!=',')return 0;
    }
    return cursor==(size_t)r->end-1;
}
static int ffr3_canonical_object(RecoveryJson *parsed,const char *raw) {
    return raw && strlen(raw)<=FFR3_MAX_RECORD && recovery_json_document(parsed,raw) &&
        ffr3_canonical_token(parsed,0);
}
static int ffr3_private_call_object(RecoveryJson *parsed,const char *raw) {
    /* Hex-encoded immutable proofs in the private keyless exchange may be
     * twice the durable 1 MiB bound. Durable schemas retain their own bound. */
    return raw && strlen(raw)<=4U*FFR3_MAX_RECORD && recovery_json_document(parsed,raw) &&
        ffr3_canonical_token(parsed,0);
}
static void ffr3_hex(const unsigned char bytes[32],char hex[65]) {
    for(size_t i=0;i<32;i++)snprintf(hex+i*2,3,"%02x",bytes[i]);
}
static int ffr3_parse_hex(const char *hex,unsigned char bytes[32]) {
    if(!valid_token(hex))return 0;
    const char *digits="0123456789abcdef";
    for(size_t i=0;i<32;i++){
        const char *a=strchr(digits,hex[i*2]);
        const char *b=strchr(digits,hex[i*2+1]);
        if(!a || !b)return 0;
        bytes[i]=(unsigned char)(((a-digits)<<4)|(b-digits));
    }
    return 1;
}
static int ffr3_fixed_kind(const char *kind,int external) {
    static const char *records[]={"CUSTODY","GUARD","CLAIM","OBSERVATION","EXIT_PROOF",
        "CHILD_INTENT","CHILD_STARTED","COMPOSITION_AUTHORITY","READY_RECEIPT","FAILURE"};
    static const char *proofs[]={"ORIGINAL_AUTHORITY","RECOVERY_AUTHORITY","ORIGINAL_CONTROLLER",
        "CONTROLLER_CAPABILITY","CONTROLLER_ADMISSION","CONTROLLER_DISPATCH","CONTROLLER_CLOSURE",
        "TARGET_ARTIFACT","PACKAGE","COMPATIBILITY","PLATFORM_OBSERVATION","ENDPOINT_CONFIGURATION","FAILURE_FACT"};
    size_t count=external?sizeof(proofs)/sizeof(proofs[0]):sizeof(records)/sizeof(records[0]);
    for(size_t i=0;i<count;i++)if(!strcmp(kind,external?proofs[i]:records[i]))return 1;
    return 0;
}
static int __attribute__((unused)) ffr3_native_codec_init(FFR3NativeCodec *codec,const char *control,
                                  const char *clock,const char *controller) {
    if(!codec || !control || !clock || !controller || strlen(clock)>=sizeof(codec->clock) ||
       strlen(controller)>=sizeof(codec->controller))return 0;
    RecoveryJson *parsed=calloc(1,sizeof(*parsed));if(!parsed)return 0;
    int valid=ffr3_canonical_object(parsed,clock) && parsed->token[0].count==3 &&
        recovery_field(parsed,0,"type","CLOCK_MONOTONIC") &&
        recovery_json_get(parsed,0,"boot_id")>=0 && recovery_json_get(parsed,0,"qualification")>=0;
    if(valid)valid=ffr3_canonical_object(parsed,controller) && parsed->token[0].count==3;
    char actual_pid[32];snprintf(actual_pid,sizeof(actual_pid),"%ld",(long)getpid());
    int birth=recovery_json_get(parsed,0,"kernel_birth");struct proc_bsdinfo info;
    memset(&info,0,sizeof(info));char seconds[32],microseconds[32];
    if(valid)valid=proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&info,sizeof(info))==(int)sizeof(info) && info.pbi_pid==(uint32_t)getpid();
    snprintf(seconds,sizeof(seconds),"%llu",(unsigned long long)info.pbi_start_tvsec);
    snprintf(microseconds,sizeof(microseconds),"%llu",(unsigned long long)info.pbi_start_tvusec);
    if(valid)valid=recovery_field(parsed,0,"pid",actual_pid) && birth>=0 && parsed->token[birth].count==2 &&
        recovery_field(parsed,birth,"seconds",seconds) && recovery_field(parsed,birth,"microseconds",microseconds) &&
        recovery_json_get(parsed,0,"runtime")>=0;
    free(parsed);if(!valid)return 0;
    long predecessor=0;char token[65]={0},expected[256];
    if(sscanf(control,"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%64[0-9a-f]",&predecessor,token)!=2 ||
       predecessor<2 || predecessor>INT_MAX || !valid_token(token))return 0;
    int count=snprintf(expected,sizeof(expected),"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%s\n",predecessor,token);
    if(count<1 || (size_t)count>=sizeof(expected) || strcmp(expected,control)){memset(token,0,sizeof(token));return 0;}
    memset(codec,0,sizeof(*codec));unsigned char digest[32];
    CC_SHA256(control,(CC_LONG)strlen(control),digest);ffr3_hex(digest,codec->key_id);
    valid=ffr3_parse_hex(token,codec->key);memset(token,0,sizeof(token));memset(expected,0,sizeof(expected));
    if(!valid){memset(codec,0,sizeof(*codec));return 0;}
    strcpy(codec->clock,clock);strcpy(codec->controller,controller);codec->predecessor=(pid_t)predecessor;
    return 1;
}
static int ffr3_native_mac(const FFR3NativeCodec *codec,const char *role,int external,
                           const char *unsigned_json,char mac[65]) {
    if(!codec || !unsigned_json || (strcmp(role,"LAUNCHER") && strcmp(role,"PREDECESSOR") && strcmp(role,"SUCCESSOR")))return 0;
    char domain[256];unsigned char derived[32],digest[32];
    int size=snprintf(domain,sizeof(domain),FFR3_PROTOCOL "/" FFR3_VERSION "/key/%s/%s",role,codec->key_id);
    if(size<0 || (size_t)size>=sizeof(domain))return 0;
    CCHmac(kCCHmacAlgSHA256,codec->key,sizeof(codec->key),domain,(size_t)size,derived);
    const char *prefix=external?FFR3_EXTERNAL "/record\n":FFR3_PROTOCOL "/" FFR3_VERSION "/record\n";
    CCHmacContext context;CCHmacInit(&context,kCCHmacAlgSHA256,derived,sizeof(derived));
    CCHmacUpdate(&context,prefix,strlen(prefix));CCHmacUpdate(&context,unsigned_json,strlen(unsigned_json));
    CCHmacFinal(&context,digest);ffr3_hex(digest,mac);memset(derived,0,sizeof(derived));return 1;
}
static size_t __attribute__((unused)) ffr3_native_encode(const FFR3NativeCodec *codec,const char *kind,int external,
                                 const char *payload,unsigned long long issued_ns,char *out,size_t capacity) {
    if(!codec || !kind || !payload || !out || !ffr3_fixed_kind(kind,external))return 0;
    RecoveryJson *parsed=calloc(1,sizeof(*parsed));if(!parsed)return 0;
    int valid=ffr3_canonical_object(parsed,payload);free(parsed);if(!valid)return 0;
    size_t bound=strlen(payload)+strlen(codec->clock)+strlen(codec->controller)+1024;
    char *unsigned_json=malloc(bound);if(!unsigned_json)return 0;
    int size=external?snprintf(unsigned_json,bound,
        "{\"clock\":%s,\"issued_ns\":\"%llu\",\"issuer\":%s,\"key_id\":\"%s\",\"kind\":\"%s\",\"payload\":%s,\"role\":\"LAUNCHER\",\"schema\":\"" FFR3_EXTERNAL "\"}",
        codec->clock,issued_ns,codec->controller,codec->key_id,kind,payload):snprintf(unsigned_json,bound,
        "{\"clock\":%s,\"issued_ns\":\"%llu\",\"key_id\":\"%s\",\"kind\":\"%s\",\"payload\":%s,\"protocol\":\"" FFR3_PROTOCOL "\",\"role\":\"LAUNCHER\",\"version\":\"" FFR3_VERSION "\"}",
        codec->clock,issued_ns,codec->key_id,kind,payload);
    char mac[65];valid=size>0 && (size_t)size<bound && ffr3_native_mac(codec,"LAUNCHER",external,unsigned_json,mac);
    if(!valid){free(unsigned_json);return 0;}
    const char *payload_field=strstr(unsigned_json,",\"payload\":");
    if(!payload_field){free(unsigned_json);return 0;}
    size_t before=(size_t)(payload_field-unsigned_json);
    int result=snprintf(out,capacity,"%.*s,\"mac\":\"%s\"%s",(int)before,unsigned_json,mac,payload_field);
    free(unsigned_json);
    size_t maximum=!strcmp(kind,"COMPOSITION_AUTHORITY")?8192:FFR3_MAX_RECORD;
    return result>0 && (size_t)result<capacity && (size_t)result<=maximum?(size_t)result:0;
}
static int __attribute__((unused)) ffr3_native_verify(const FFR3NativeCodec *codec,const char *raw,int external) {
    if(!codec || !raw)return 0;
    RecoveryJson *parsed=calloc(1,sizeof(*parsed));if(!parsed)return 0;
    char role[32],key[65],mac[65],actual[65]={0};
    int valid=ffr3_canonical_object(parsed,raw) && parsed->token[0].count==9 &&
        recovery_string(parsed,0,"role",role,sizeof(role)) && recovery_string(parsed,0,"key_id",key,sizeof(key)) &&
        !strcmp(key,codec->key_id) && recovery_string(parsed,0,"mac",mac,sizeof(mac)) && valid_token(mac) &&
        (external?recovery_field(parsed,0,"schema",FFR3_EXTERNAL):
         (recovery_field(parsed,0,"protocol",FFR3_PROTOCOL) && recovery_field(parsed,0,"version",FFR3_VERSION)));
    int clock=recovery_json_get(parsed,0,"clock"),field=recovery_json_get(parsed,0,"mac");
    if(valid)valid=clock>=0 && field>0 && ffr3_token_end(parsed,clock)-ffr3_token_start(parsed,clock)==strlen(codec->clock) &&
        !memcmp(raw+ffr3_token_start(parsed,clock),codec->clock,strlen(codec->clock));
    if(!valid){free(parsed);return 0;}
    size_t start=ffr3_token_start(parsed,field-1),end=ffr3_token_end(parsed,field);
    if(start<1 || raw[start-1]!=','){free(parsed);return 0;}
    char *unsigned_json=malloc(strlen(raw)+1);if(!unsigned_json){free(parsed);return 0;}
    memcpy(unsigned_json,raw,start-1);strcpy(unsigned_json+start-1,raw+end);
    valid=ffr3_native_mac(codec,role,external,unsigned_json,actual);
    unsigned char difference=0;for(size_t i=0;i<64;i++)difference|=(unsigned char)(actual[i]^mac[i]);
    free(unsigned_json);free(parsed);return valid && difference==0;
}

/* Fixed estate I/O mirrors RecoveryStore's private immutable record rules. */
static int ffr3_private_directory(int descriptor) {
    struct stat info;
    return fstat(descriptor,&info)==0 && S_ISDIR(info.st_mode) &&
        info.st_uid==geteuid() && (info.st_mode&0777)==0700;
}
static int ffr3_same_file(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_mode==b->st_mode &&
        a->st_uid==b->st_uid && a->st_nlink==b->st_nlink && a->st_size==b->st_size &&
        a->st_mtimespec.tv_sec==b->st_mtimespec.tv_sec && a->st_mtimespec.tv_nsec==b->st_mtimespec.tv_nsec &&
        a->st_ctimespec.tv_sec==b->st_ctimespec.tv_sec && a->st_ctimespec.tv_nsec==b->st_ctimespec.tv_nsec;
}
static int ffr3_budget(const struct timespec *stop) {
    struct timespec now;
    return stop && clock_gettime(CLOCK_MONOTONIC,&now)==0 && !time_reached(&now,stop);
}
static char *ffr3_capture_at(int parent,const char *name,size_t limit,size_t *length,
                             int private_file,const struct timespec *stop) {
    if(!name || strchr(name,'/') || !ffr3_budget(stop))return NULL;
    int descriptor=openat(parent,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(descriptor<0)return NULL;
    struct stat before,named,after;char *raw=NULL;
    if(fstat(descriptor,&before)!=0 || !S_ISREG(before.st_mode) || before.st_nlink!=1 ||
       before.st_size<0 || (private_file>=0 && before.st_size<1) || (unsigned long long)before.st_size>limit ||
       (private_file>0 && (before.st_uid!=geteuid() || (before.st_mode&0777)!=0600)) ||
       fstatat(parent,name,&named,AT_SYMLINK_NOFOLLOW)!=0 || !ffr3_same_file(&before,&named))goto done;
    raw=malloc((size_t)before.st_size+1);if(!raw)goto done;
    size_t offset=0;
    while(offset<(size_t)before.st_size){
        if(!ffr3_budget(stop)){free(raw);raw=NULL;goto done;}
        ssize_t size=read(descriptor,raw+offset,(size_t)before.st_size-offset);
        if(size<0 && errno==EINTR)continue;
        if(size<=0){free(raw);raw=NULL;goto done;}offset+=(size_t)size;
    }
    char extra;
    if(read(descriptor,&extra,1)!=0 || fstat(descriptor,&after)!=0 || !ffr3_same_file(&before,&after) ||
       fstatat(parent,name,&named,AT_SYMLINK_NOFOLLOW)!=0 || !ffr3_same_file(&before,&named) || !ffr3_budget(stop)){
        free(raw);raw=NULL;goto done;
    }
    raw[offset]=0;*length=offset;
done: close(descriptor);return raw;
}
static int __attribute__((unused)) ffr3_publish_immutable(int parent,const char *name,const char *raw,
                                      size_t length,const struct timespec *stop) {
    if(!name || !raw || !length || length>FFR3_MAX_RECORD || strchr(name,'/') ||
       !ffr3_private_directory(parent) || !ffr3_budget(stop))return 0;
    struct stat directory_before,directory_after;
    if(fstat(parent,&directory_before)!=0)return 0;
    int descriptor=openat(parent,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(descriptor<0)return 0;
    int valid=1;size_t offset=0;struct stat before,named;
    while(offset<length){
        if(!ffr3_budget(stop)){valid=0;break;}
        ssize_t size=write(descriptor,raw+offset,length-offset);
        if(size<0 && errno==EINTR)continue;
        if(size<=0){valid=0;break;}offset+=(size_t)size;
    }
    if(valid)valid=fsync(descriptor)==0 && fstat(descriptor,&before)==0 && S_ISREG(before.st_mode) &&
        before.st_nlink==1 && before.st_uid==geteuid() && (before.st_mode&0777)==0600 &&
        before.st_size==(off_t)length && fstatat(parent,name,&named,AT_SYMLINK_NOFOLLOW)==0 && ffr3_same_file(&before,&named);
    close(descriptor);
    if(!valid || fsync(parent)!=0 || !ffr3_budget(stop))return 0;
    size_t count=0;char *readback=ffr3_capture_at(parent,name,length,&count,1,stop);
    valid=readback && count==length && !memcmp(readback,raw,length) &&
        fstat(parent,&directory_after)==0 && directory_before.st_dev==directory_after.st_dev &&
        directory_before.st_ino==directory_after.st_ino && directory_before.st_mode==directory_after.st_mode &&
        directory_before.st_uid==directory_after.st_uid;
    free(readback);return valid && ffr3_budget(stop);
}
static int __attribute__((unused)) ffr3_publish_record(int records,const FFR3NativeCodec *codec,
                         const char *raw,const char *kind,int external,const struct timespec *stop,char digest[65]) {
    if(!ffr3_native_verify(codec,raw,external) || !ffr3_fixed_kind(kind,external))return 0;
    RecoveryJson *parsed=calloc(1,sizeof(*parsed));if(!parsed)return 0;
    int valid=ffr3_canonical_object(parsed,raw) && recovery_field(parsed,0,"kind",kind);free(parsed);
    if(!valid || (!external && (!strcmp(kind,"COMPOSITION_AUTHORITY") || !strcmp(kind,"CHILD_IDENTITY") ||
       !strcmp(kind,"GUARD") || !strcmp(kind,"CLAIM") || !strcmp(kind,"CHILD_INTENT"))))return 0;
    unsigned char hash[32];CC_SHA256(raw,(CC_LONG)strlen(raw),hash);ffr3_hex(hash,digest);
    char name[160];int size=external?snprintf(name,sizeof(name),"%s.blob",digest):snprintf(name,sizeof(name),"%s-%s.json",kind,digest);
    return size>0 && (size_t)size<sizeof(name) && ffr3_publish_immutable(records,name,raw,strlen(raw),stop);
}
/* Native entry below owns the prospective controller ledger, its original
 * private helper exchange, and irreversible closure. The immutable publisher
 * alone never confers controller, child, or composition authority. */
/* R3's independently prepared fixed estate is a source-owned trust boundary.
 * Acquisition never accepts an anchor hash, approval, path or catalogue from
 * argv/environment/HTTP. The offline publisher is independently authorized;
 * these native checks do not manufacture that human attribution. */
static char *ffr3_json_value(const RecoveryJson *j,int token) {
    if(token<0)return NULL;size_t a=ffr3_token_start(j,token),b=ffr3_token_end(j,token);
    char *out=malloc(b-a+1);if(!out)return NULL;memcpy(out,j->text+a,b-a);out[b-a]=0;return out;
}
static char *ffr3_json_field(const char *raw,const char *key) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return NULL;
    char *out=ffr3_canonical_object(j,raw)?ffr3_json_value(j,recovery_json_get(j,0,key)):NULL;free(j);return out;
}
static int ffr3_id(const char *value) {
    if(!value || !*value || strlen(value)>128)return 0;
    for(size_t i=0;value[i];i++)if(!((value[i]>='A'&&value[i]<='Z') || (value[i]>='a'&&value[i]<='z') ||
      (value[i]>='0'&&value[i]<='9') || (i && strchr("._:-",value[i]))))return 0;
    return 1;
}
static int ffr3_json_string_value(const char *raw,const char *field,char *out,size_t capacity) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return 0;
    int valid=ffr3_canonical_object(j,raw) && recovery_string(j,0,field,out,capacity);free(j);return valid;
}
static int ffr3_child_directory(int parent,const char *name) {
    int fd=openat(parent,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(fd>=0 && !ffr3_private_directory(fd)){close(fd);fd=-1;}return fd;
}
static DIR *ffr3_directory_stream(int descriptor) {
    /* A distinct open description preserves full enumeration on every
     * observation. dup() would consume the retained descriptor's offset. */
    int scan=openat(descriptor,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(scan<0)return NULL;struct stat original,current;
    if(fstat(descriptor,&original)!=0||fstat(scan,&current)!=0||
       original.st_dev!=current.st_dev||original.st_ino!=current.st_ino||
       !ffr3_private_directory(scan)){close(scan);return NULL;}
    DIR *stream=fdopendir(scan);if(!stream)close(scan);return stream;
}
static char *ffr3_blob_at(int directory,const char *blob,const char *suffix,const struct timespec *stop) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return NULL;
    char hash[65],count[32],name[96];
    int valid=ffr3_canonical_object(j,blob) && j->token[0].count==3 &&
        recovery_string(j,0,"hash",hash,sizeof(hash)) && valid_token(hash) &&
        recovery_string(j,0,"bytes",count,sizeof(count));free(j);
    if(!valid || !*count || strspn(count,"0123456789")!=strlen(count) || (count[0]=='0'&&count[1]))return NULL;
    errno=0;char *end=NULL;unsigned long long expected=strtoull(count,&end,10);
    if(errno || !end || *end || expected<1 || expected>16U*FFR3_MAX_RECORD)return NULL;
    if(snprintf(name,sizeof(name),"%s.%s",hash,suffix)>=(int)sizeof(name))return NULL;
    size_t bytes=0;char *raw=ffr3_capture_at(directory,name,(size_t)expected,&bytes,1,stop);
    unsigned char digest[32];char actual[65];
    if(raw){CC_SHA256(raw,(CC_LONG)bytes,digest);ffr3_hex(digest,actual);}
    if(!raw || bytes!=expected || strcmp(actual,hash)){free(raw);return NULL;}return raw;
}
static int ffr3_actual_native_process(char out[1024],char executable_hash[65],size_t *executable_size) {
    char image[PATH_MAX];uint32_t size=sizeof(image);
    if(_NSGetExecutablePath(image,&size)!=0 || !canonical_image_path(image))return 0;
    struct proc_bsdinfo process;memset(&process,0,sizeof(process));
    if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&process,sizeof(process))!=(int)sizeof(process) || process.pbi_pid!=(uint32_t)getpid())return 0;
    int fd=open(canonical_executable,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return 0;
    struct stat before,after,named;int valid=fstat(fd,&before)==0 && S_ISREG(before.st_mode) && before.st_nlink==1 &&
       before.st_size>0 && before.st_size<=16*FFR3_MAX_RECORD && lstat(canonical_executable,&named)==0 && ffr3_same_file(&before,&named);
    uint64_t address=0;int mapped=0;
    for(int index=0;valid && index<4096;index++){
        struct proc_regionwithpathinfo region;memset(&region,0,sizeof(region));
        if(proc_pidinfo(getpid(),PROC_PIDREGIONPATHINFO,address,&region,sizeof(region))!=(int)sizeof(region)){valid=0;break;}
        if((region.prp_prinfo.pri_protection&4) && !strcmp(region.prp_vip.vip_path,canonical_executable)){
            mapped=region.prp_vip.vip_vi.vi_stat.vst_ino==(uint64_t)before.st_ino &&
                region.prp_vip.vip_vi.vi_stat.vst_dev==(uint32_t)before.st_dev;break;
        }
        uint64_t next=region.prp_prinfo.pri_address+region.prp_prinfo.pri_size;
        if(next<=address){valid=0;break;}address=next;
    }
    CC_SHA256_CTX context;CC_SHA256_Init(&context);unsigned char block[65536],digest[32];size_t total=0;
    while(valid){ssize_t n=read(fd,block,sizeof(block));if(n<0 && errno==EINTR)continue;if(n<0){valid=0;break;}
        if(n==0)break;total+=(size_t)n;if(total>(size_t)before.st_size){valid=0;break;}CC_SHA256_Update(&context,block,(CC_LONG)n);}
    if(valid)valid=mapped && total==(size_t)before.st_size && fstat(fd,&after)==0 && ffr3_same_file(&before,&after) &&
       lstat(canonical_executable,&named)==0 && ffr3_same_file(&before,&named);
    close(fd);
    if(!valid)return 0;CC_SHA256_Final(digest,&context);ffr3_hex(digest,executable_hash);*executable_size=total;
    int n=snprintf(out,1024,"{\"kernel_birth\":{\"microseconds\":\"%llu\",\"seconds\":\"%llu\"},\"pid\":\"%ld\",\"runtime\":\"%s\"}",
        (unsigned long long)process.pbi_start_tvusec,(unsigned long long)process.pbi_start_tvsec,(long)getpid(),executable_hash);
    return n>0 && n<1024;
}
typedef struct FFR3PreparedNative {
    int root,preparation,preparation_records,blobs,records,lock;
    char controller[1024],executable_hash[65];size_t executable_size;
    char *pin,*approval,*record,*catalogue,*selector,*mode,*clock,*lineage,*attempt,*helper_plan,*helper_plan_blob,*artifact;
    struct timespec origin,stop;
} FFR3PreparedNative;
static void ffr3_release_preparation(FFR3PreparedNative *p) {
    free(p->pin);free(p->approval);free(p->record);free(p->catalogue);free(p->selector);free(p->mode);free(p->clock);
    free(p->lineage);free(p->attempt);free(p->helper_plan);free(p->helper_plan_blob);free(p->artifact);
    int *fds[]={&p->root,&p->preparation,&p->preparation_records,&p->blobs,&p->records,&p->lock};
    for(size_t i=0;i<sizeof(fds)/sizeof(fds[0]);i++)if(*fds[i]>=0){close(*fds[i]);*fds[i]=-1;}
}
static int ffr3_fixed_estate(char path[PATH_MAX]) {
    struct passwd *account=getpwuid(geteuid());
    return account && account->pw_dir && snprintf(path,PATH_MAX,"%s/Library/Application Support/KRONOS/runtime/recovery-v1",account->pw_dir)<PATH_MAX && recovery_safe_path(path,1,1);
}
static int ffr3_set_native_home(void) {
    struct passwd *account=getpwuid(geteuid());
    return account&&account->pw_dir&&account->pw_dir[0]=='/'&&setenv("HOME",account->pw_dir,1)==0;
}
static int ffr3_pin_selector(const char *pin,char **selector,char digest[65]) {
    char *attempt=ffr3_json_field(pin,"attempt"),*installation=ffr3_json_field(pin,"installation"),*lineage=ffr3_json_field(pin,"lineage"),
         *mode=ffr3_json_field(pin,"mode"),*service=ffr3_json_field(pin,"service");
    size_t bound=(attempt?strlen(attempt):0)+(installation?strlen(installation):0)+(lineage?strlen(lineage):0)+(mode?strlen(mode):0)+(service?strlen(service):0)+128;
    char *raw=malloc(bound);int valid=raw && attempt && installation && lineage && mode && service;
    if(valid){int n=snprintf(raw,bound,"{\"attempt\":%s,\"installation\":%s,\"lineage\":%s,\"mode\":%s,\"service\":%s}",attempt,installation,lineage,mode,service);
        valid=n>0 && (size_t)n<bound;if(valid){unsigned char hash[32];CC_SHA256(raw,(CC_LONG)n,hash);ffr3_hex(hash,digest);}}
    free(attempt);free(installation);free(lineage);free(mode);free(service);if(!valid){free(raw);return 0;}*selector=raw;return 1;
}
static int ffr3_select_preparation(FFR3PreparedNative *p) {
    DIR *directory=ffr3_directory_stream(p->preparation);if(!directory)return 0;
    struct dirent *entry;size_t seen=0,matches=0;int valid=1;
    while(valid && (entry=readdir(directory))){
        const char *name=entry->d_name;if(!strcmp(name,".")||!strcmp(name,"..")||!strcmp(name,"records"))continue;
        if(++seen>8192){valid=0;break;}
        size_t length=strlen(name);
        if(length==73 && !strcmp(name+64,".approval")){char hash[65];memcpy(hash,name,64);hash[64]=0;if(!valid_token(hash))valid=0;continue;}
        if(length!=68 || strcmp(name+64,".pin")){valid=0;break;}
        char expected[65];memcpy(expected,name,64);expected[64]=0;if(!valid_token(expected)){valid=0;break;}
        size_t bytes=0;char *pin=ffr3_capture_at(p->preparation,name,FFR3_MAX_RECORD,&bytes,1,&p->stop);
        RecoveryJson *j=calloc(1,sizeof(*j));char actual[65],*selector=NULL,*reference=NULL,*record=NULL;
        if(!pin || !j || !ffr3_canonical_object(j,pin) || j->token[0].count!=8 ||
           !recovery_field(j,0,"schema","KRONOS-FAILED-FENCED-PREPARATION-PIN/1.0.0") ||
           !ffr3_pin_selector(pin,&selector,actual) || strcmp(actual,expected)){valid=0;}
        if(valid){reference=ffr3_json_field(pin,"preparation");record=reference?ffr3_blob_at(p->preparation_records,reference,"json",&p->stop):NULL;
            valid=record && ffr3_canonical_object(j,record) && j->token[0].count==15 &&
                recovery_field(j,0,"schema","KRONOS-FAILED-FENCED-CONTROL-PREPARATION/1.0.0");}
        if(valid){char *controller=ffr3_json_field(record,"controller");
            if(controller && !strcmp(controller,p->controller)){
                if(++matches!=1)valid=0;
                else{p->pin=pin;pin=NULL;p->record=record;record=NULL;p->selector=selector;selector=NULL;
                    char approval_name[96];snprintf(approval_name,sizeof(approval_name),"%s.approval",expected);
                    p->approval=ffr3_capture_at(p->preparation,approval_name,FFR3_MAX_RECORD,&bytes,1,&p->stop);
                    char *catalogue_ref=ffr3_json_field(p->pin,"catalogue");p->catalogue=catalogue_ref?ffr3_blob_at(p->preparation_records,catalogue_ref,"json",&p->stop):NULL;free(catalogue_ref);
                    valid=p->approval && p->catalogue;
                }}free(controller);}
        free(j);free(pin);free(selector);free(reference);free(record);
    }
    closedir(directory);if(!valid || matches!=1)return 0;
    p->mode=ffr3_json_field(p->record,"mode");p->clock=ffr3_json_field(p->record,"clock");
    p->lineage=ffr3_json_field(p->record,"lineage");p->attempt=ffr3_json_field(p->record,"attempt");
    return p->mode && p->clock && p->lineage && p->attempt;
}
static int ffr3_stage_retained_facts(void);
static int ffr3_fact_payload(const char *kind,const char *payload);
static int __attribute__((unused)) ffr3_native_stage(FFR3PreparedNative *p,int wait_for_preparation) {
    memset(p,0,sizeof(*p));p->root=p->preparation=p->preparation_records=p->blobs=p->records=p->lock=-1;
    if(!ffr3_actual_native_process(p->controller,p->executable_hash,&p->executable_size))return 0;
    char estate[PATH_MAX];if(!ffr3_fixed_estate(estate))return 0;
    p->root=open(estate,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(p->root<0 || !ffr3_private_directory(p->root))goto failed;
    p->preparation=ffr3_child_directory(p->root,"preparation");if(p->preparation<0)goto failed;
    if(wait_for_preparation){
        /* Inert offline staging: no helper, reservation, dispatch or product
         * effect. One filesystem event is only a wakeup, never authority. */
        int queue=kqueue();if(queue<0)goto failed;
        struct kevent change,event;EV_SET(&change,(uintptr_t)p->preparation,EVFILT_VNODE,EV_ADD|EV_CLEAR|EV_ONESHOT,NOTE_WRITE|NOTE_RENAME|NOTE_DELETE,0,NULL);
        if(kevent(queue,&change,1,NULL,0,NULL)!=0){close(queue);goto failed;}
        /* Arm before advertising identity/facts so an immediate trusted
         * publisher cannot race past the one acquisition notification. */
        puts(p->controller);fflush(stdout);
        /* Retained facts are inert proposals for the later exact offline
         * decision. This performs no helper, source/signature/epoch check,
         * reservation or operation, and preserves original verified times. */
        if(!ffr3_stage_retained_facts()){close(queue);goto failed;}
        int n=kevent(queue,NULL,0,&event,1,NULL);close(queue);
        if(n!=1 || event.flags&EV_ERROR || event.fflags&(NOTE_RENAME|NOTE_DELETE))goto failed;
    }
    /* Shared origin precedes lock/preflight and the first operational helper. */
    if(clock_gettime(CLOCK_MONOTONIC,&p->origin)!=0)goto failed;p->stop=p->origin;p->stop.tv_sec+=15;
    char actual_controller[1024],actual_image[65];size_t actual_size=0;
    if(!ffr3_actual_native_process(actual_controller,actual_image,&actual_size)||
       strcmp(actual_controller,p->controller)||strcmp(actual_image,p->executable_hash)||actual_size!=p->executable_size)goto failed;
    p->lock=openat(p->root,"service.lock",O_RDWR|O_NOFOLLOW|O_CLOEXEC);
    if(p->lock<0)goto failed;struct stat lock;
    if(fstat(p->lock,&lock)!=0 || !S_ISREG(lock.st_mode) || lock.st_uid!=geteuid() || lock.st_nlink!=1 || (lock.st_mode&0777)!=0600)goto failed;
    while(flock(p->lock,LOCK_EX|LOCK_NB)!=0){if(errno!=EWOULDBLOCK || !ffr3_budget(&p->stop))goto failed;struct timespec pause={0,1000000};nanosleep(&pause,NULL);}
    p->preparation_records=ffr3_child_directory(p->preparation,"records");p->blobs=ffr3_child_directory(p->root,"blobs");p->records=ffr3_child_directory(p->root,"records");
    if(p->preparation_records<0 || p->blobs<0 || p->records<0 || !ffr3_select_preparation(p))goto failed;
    return ffr3_budget(&p->stop);
failed:ffr3_release_preparation(p);return 0;
}

static unsigned long long ffr3_now_ns(void) {
    struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0 || now.tv_sec<0 ||
      (unsigned long long)now.tv_sec>(ULLONG_MAX-(unsigned long long)now.tv_nsec)/1000000000ULL)return 0;
    return (unsigned long long)now.tv_sec*1000000000ULL+(unsigned long long)now.tv_nsec;
}
static int ffr3_kernel_boot(const char *clock) {
    char boot[128];size_t bytes=sizeof(boot);
    return sysctlbyname("kern.bootsessionuuid",boot,&bytes,NULL,0)==0 && bytes>1 && bytes<=sizeof(boot) &&
        boot[bytes-1]==0 && strlen(boot)+1==bytes && ffr3_id(boot) && ffr3_json_string_value(clock,"boot_id",(char[128]){0},128) &&
        ({char prepared_boot[128];ffr3_json_string_value(clock,"boot_id",prepared_boot,sizeof(prepared_boot)) && !strcmp(boot,prepared_boot);});
}
static int ffr3_select_launcher_artifact(FFR3PreparedNative *p) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return 0;
    if(!ffr3_canonical_object(j,p->catalogue)){free(j);return 0;}
    int rows=recovery_json_get(j,0,"rows");if(rows<0 || j->token[rows].kind!='['){free(j);return 0;}
    char *source=ffr3_json_field(p->record,"launcher_source"),*package=ffr3_json_field(p->record,"launcher_package");
    if(!source||!package){free(source);free(package);free(j);return 0;}
    unsigned matches=0;
    for(int item=rows+1;item<j->token[rows].next;item=j->token[item].next){
        if(!recovery_field(j,item,"purpose","ARTIFACT") || !recovery_field(j,item,"authority","CA"))continue;
        int binding=recovery_json_get(j,item,"bindings"),exe=recovery_json_get(j,binding,"executable");
        char hash[65],bytes[32],actual_bytes[32];snprintf(actual_bytes,sizeof(actual_bytes),"%zu",p->executable_size);
        char *candidate_source=ffr3_json_value(j,recovery_json_get(j,binding,"source_inventory"));
        char *candidate_package=ffr3_json_value(j,recovery_json_get(j,binding,"package"));
        int match=candidate_source && candidate_package && !strcmp(candidate_source,source) && !strcmp(candidate_package,package) &&
            recovery_string(j,exe,"hash",hash,sizeof(hash)) && !strcmp(hash,p->executable_hash) &&
            recovery_string(j,exe,"bytes",bytes,sizeof(bytes)) && !strcmp(bytes,actual_bytes);
        free(candidate_source);free(candidate_package);
        if(match){
            if(++matches!=1)break;p->artifact=ffr3_json_value(j,item);
            p->helper_plan_blob=ffr3_json_value(j,recovery_json_get(j,binding,"bootstrap_plan"));
            if(p->helper_plan_blob)p->helper_plan=ffr3_blob_at(p->blobs,p->helper_plan_blob,"blob",&p->stop);
        }
    }
    free(j);free(source);free(package);
    if(matches!=1 || !p->artifact || !p->helper_plan || !p->helper_plan_blob)return 0;
    j=calloc(1,sizeof(*j));if(!j)return 0;
    int valid=ffr3_canonical_object(j,p->helper_plan) && j->token[0].count==5 &&
       recovery_field(j,0,"schema","KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0");
    char *approved=ffr3_json_field(p->record,"launcher_source"),*planned=ffr3_json_field(p->helper_plan,"source_inventory");
    valid=valid&&approved&&planned&&!strcmp(approved,planned);free(approved);free(planned);free(j);return valid;
}
static char *__attribute__((unused)) ffr3_native_capability(FFR3PreparedNative *p,FFR3NativeCodec *codec) {
    if(!ffr3_budget(&p->stop) || !ffr3_kernel_boot(p->clock) || !ffr3_select_launcher_artifact(p))return NULL;
    int parent=openat(p->root,"..",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(parent<0 || !ffr3_private_directory(parent)){if(parent>=0)close(parent);return NULL;}
    size_t bytes=0;char *control=ffr3_capture_at(parent,"browser-backend-v1.control",255,&bytes,1,&p->stop);close(parent);
    if(!control || !ffr3_native_codec_init(codec,control,p->clock,p->controller)){if(control){memset(control,0,bytes);free(control);}return NULL;}
    memset(control,0,bytes);free(control);
    char digest[65];if(!ffr3_json_string_value(p->record,"control_hash",digest,sizeof(digest)) || strcmp(digest,codec->key_id))return NULL;
    char *source=ffr3_json_field(p->record,"launcher_source"),*package=ffr3_json_field(p->record,"launcher_package"),
        *predecessor=ffr3_json_field(p->lineage,"predecessor"),*binding=ffr3_json_field(p->artifact,"bindings"),
        *qualified=ffr3_json_field(p->artifact,"identity"),*executable=binding?ffr3_json_field(binding,"executable"):NULL;
    unsigned char hash[32];CC_SHA256(p->controller,(CC_LONG)strlen(p->controller),hash);ffr3_hex(hash,digest);
    const char *actions[]={"AUTHORIZE","CHILD_FORK","CHILD_INTENT","CONSUME","DISPATCH_SHUTDOWN","RELEASE_COMPOSITION","RESERVE_ORIGINAL",
        "VERIFY_CONTINUITY","VERIFY_EXIT","VERIFY_HANDOFF","VERIFY_PACKAGE","VERIFY_SOURCE","VERIFY_STATUS","WAIT_DRAIN"};
    size_t bound=source&&package&&predecessor&&binding&&qualified&&executable?
      strlen(source)+strlen(package)+strlen(predecessor)+strlen(qualified)+strlen(executable)*2+strlen(p->controller)+strlen(p->mode)+
      (strlen(p->helper_plan_blob)+128)*14+4096:0;
    char *payload=bound?malloc(bound):NULL,*raw=malloc(FFR3_MAX_RECORD+1);char operations[32768];size_t used=0;operations[used++]='[';
    int valid=payload && raw;
    for(size_t i=0;valid && i<sizeof(actions)/sizeof(actions[0]);i++){
        int n=snprintf(operations+used,sizeof(operations)-used,"%s{\"action\":\"%s\",\"implementation\":%s}",i?",":"",actions[i],source);
        valid=n>0 && (size_t)n<sizeof(operations)-used;if(valid)used+=(size_t)n;
    }
    if(valid){operations[used++]=']';operations[used]=0;unsigned long long now=ffr3_now_ns();
        int n=snprintf(payload,bound,"{\"controller\":%s,\"executable\":%s,\"execution_lock\":\"native-controller-%s\",\"identity\":\"controller-capability-%s\",\"ledger_schema\":\"KRONOS-FAILED-FENCED-CONTROLLER-LEDGER/1.0.0\",\"operations\":%s,\"package\":%s,\"phase\":%s,\"predecessor\":%s,\"proof_publication\":%s,\"qualified_artifact\":%s,\"source_inventory\":%s,\"verified_ns\":\"%llu\"}",
            p->controller,executable,digest,digest,operations,package,p->mode,predecessor,executable,qualified,source,now);
        valid=n>0 && (size_t)n<bound && ffr3_native_encode(codec,"CONTROLLER_CAPABILITY",1,payload,now,raw,FFR3_MAX_RECORD+1)>0;
    }
    if(valid)valid=ffr3_publish_record(p->blobs,codec,raw,"CONTROLLER_CAPABILITY",1,&p->stop,digest);
    free(source);free(package);free(predecessor);free(binding);free(qualified);free(executable);free(payload);
    if(!valid){free(raw);return NULL;}return raw;
}

typedef struct FFR3Buffer {char *bytes;size_t used,capacity;} FFR3Buffer;
static int ffr3_append(FFR3Buffer *b,const char *value,size_t n) {
    if(n>64U*1024U*1024U-b->used-1)return 0;
    size_t need=b->used+n+1;
    if(need>b->capacity){size_t capacity=b->capacity?b->capacity:4096;while(capacity<need)capacity*=2;
        if(capacity>64U*1024U*1024U)capacity=64U*1024U*1024U;char *next=realloc(b->bytes,capacity);if(!next)return 0;b->bytes=next;b->capacity=capacity;}
    memcpy(b->bytes+b->used,value,n);b->used+=n;b->bytes[b->used]=0;return 1;
}
static int ffr3_text(FFR3Buffer *b,const char *value){return value && ffr3_append(b,value,strlen(value));}
static int ffr3_quote(FFR3Buffer *b,const char *value) {
    if(!ffr3_text(b,"\""))return 0;
    for(size_t i=0;value[i];i++){
        unsigned char c=(unsigned char)value[i];if(c<32 || c>126)return 0;
        if((c=='"'||c=='\\') && !ffr3_text(b,"\\"))return 0;
        if(!ffr3_append(b,value+i,1))return 0;
    }
    return ffr3_text(b,"\"");
}
static int ffr3_module_path(const char *repository,const char *name,char path[PATH_MAX],int *package) {
    if(!name || !*name || strlen(name)>127 || (strcmp(name,"kronos") && strncmp(name,"kronos.",7) && strncmp(name,"tools.",6)))return 0;
    char relative[256];size_t n=strlen(name);
    for(size_t i=0;i<n;i++){char c=name[i];if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='.') ||
        (c=='.' && (!i || name[i-1]=='.' || !name[i+1])))return 0;
        relative[i]=c=='.'?'/':c;}
    relative[n]=0;
    const char *prefix=!strncmp(name,"kronos",6)?"src/":"";
    char file[PATH_MAX],folder[PATH_MAX],resolved[PATH_MAX];struct stat a,b;
    if(snprintf(file,sizeof(file),"%s/%s%s.py",repository,prefix,relative)>=(int)sizeof(file) ||
       snprintf(folder,sizeof(folder),"%s/%s%s/__init__.py",repository,prefix,relative)>=(int)sizeof(folder))return 0;
    int plain=lstat(file,&a)==0,pkg=lstat(folder,&b)==0;
    if(plain==pkg)return 0;const char *chosen=plain?file:folder;
    if(!realpath(chosen,resolved) || strcmp(chosen,resolved) || !recovery_safe_path(chosen,0,0))return 0;
    strcpy(path,chosen);*package=pkg;return 1;
}
static char *ffr3_format(const char *format,...);

/* Complete approved capture and exact executed BootstrapPlan are distinct. */
static char *ffr3_capture_inventory(FFR3PreparedNative *p,const char *plan,char **inventory) {
    char *ref=ffr3_json_field(plan,"source_inventory");
    *inventory=ref?ffr3_blob_at(p->blobs,ref,"blob",&p->stop):NULL;free(ref);
    char *wrapped=*inventory?ffr3_format("{\"modules\":%s}",*inventory):NULL;
    RecoveryJson *j=calloc(1,sizeof(*j));FFR3Buffer out={0};
    int valid=j&&wrapped&&ffr3_canonical_object(j,wrapped);
    int list=valid?recovery_json_get(j,0,"modules"):-1;
    valid=valid&&list>=0&&j->token[list].kind=='['&&j->token[list].count>0&&j->token[list].count<=4096&&ffr3_text(&out,"{\"modules\":[");
    unsigned count=0;
    for(int row=list+1;valid&&row<j->token[list].next;row=j->token[row].next){
        int name=row+1,digest=j->token[name].next;
        valid=j->token[row].kind=='['&&j->token[row].count==2&&j->token[name].kind=='s'&&j->token[digest].kind=='s';
        char *n=valid?ffr3_json_value(j,name):NULL,*d=valid?ffr3_json_value(j,digest):NULL;
        valid=valid&&n&&d&&ffr3_text(&out,count++?",{\"digest\":":"{\"digest\":")&&ffr3_text(&out,d)&&ffr3_text(&out,",\"name\":")&&ffr3_text(&out,n)&&ffr3_text(&out,"}");
        free(n);free(d);
    }
    valid=valid&&ffr3_text(&out,"]}")&&ffr3_budget(&p->stop);free(j);free(wrapped);
    if(!valid){free(out.bytes);free(*inventory);*inventory=NULL;return NULL;}return out.bytes;
}

static char *__attribute__((unused)) ffr3_build_pin_frame(FFR3PreparedNative *p,const char *repository,char helper_entry[512],size_t *length) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return NULL;
    char *inventory=NULL,*capture=ffr3_capture_inventory(p,p->helper_plan,&inventory);
    int parsed=capture&&ffr3_canonical_object(j,capture);
    if(!parsed){free(capture);free(inventory);free(j);return NULL;}
    int modules=recovery_json_get(j,0,"modules");if(modules<0 || j->token[modules].kind!='[' || j->token[modules].count>4096){free(capture);free(inventory);free(j);return NULL;}
    char plan_hash[65];if(!ffr3_json_string_value(p->helper_plan_blob,"hash",plan_hash,sizeof(plan_hash))){free(capture);free(inventory);free(j);return NULL;}
    FFR3Buffer buffer={0};int valid=ffr3_text(&buffer,"{\"inventory\":") && ffr3_text(&buffer,inventory) && ffr3_text(&buffer,",\"plan\":") && ffr3_text(&buffer,p->helper_plan) &&
       ffr3_text(&buffer,",\"plan_hash\":") && ffr3_quote(&buffer,plan_hash) && ffr3_text(&buffer,",\"sources\":[");
    char previous[128]={0};unsigned count=0;int entry_seen=0;
    for(int row=modules+1;valid && row<j->token[modules].next;row=j->token[row].next){
        char name[128],expected[65],path[PATH_MAX];int package=0;
        valid=j->token[row].kind=='{' && j->token[row].count==2 && recovery_string(j,row,"name",name,sizeof(name)) &&
          recovery_string(j,row,"digest",expected,sizeof(expected)) && valid_token(expected) &&
          (!*previous || strcmp(previous,name)<0) && ffr3_module_path(repository,name,path,&package) && ffr3_budget(&p->stop);
        if(!valid)break;strcpy(previous,name);
        char parent_path[PATH_MAX];strcpy(parent_path,path);char *slash=strrchr(parent_path,'/');if(!slash){valid=0;break;}*slash=0;
        int parent=open(parent_path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);size_t bytes=0;
        char *raw=parent>=0?ffr3_capture_at(parent,slash+1,16U*FFR3_MAX_RECORD,&bytes,-1,&p->stop):NULL;if(parent>=0)close(parent);
        unsigned char digest[32];char actual[65];if(raw){CC_SHA256(raw,(CC_LONG)bytes,digest);ffr3_hex(digest,actual);}
        if(!raw || strcmp(actual,expected)){free(raw);valid=0;break;}
        valid=ffr3_text(&buffer,count++?",{\"name\":":"{\"name\":") && ffr3_quote(&buffer,name) &&
          ffr3_text(&buffer,package?",\"package\":true,\"path\":":",\"package\":false,\"path\":") && ffr3_quote(&buffer,path) && ffr3_text(&buffer,",\"payload\":\"");
        const char *hex="0123456789abcdef";
        for(size_t i=0;valid && i<bytes;i++){char encoded[2]={hex[(unsigned char)raw[i]>>4],hex[(unsigned char)raw[i]&15]};valid=ffr3_append(&buffer,encoded,2);}
        valid=valid && ffr3_text(&buffer,"\"}");
        if(!strcmp(name,"tools.failed_fenced_launcher")){
            int n=snprintf(helper_entry,512,"{\"bytes\":\"%zu\",\"hash\":\"%s\",\"identity\":\"native-helper-entry\"}",bytes,actual);entry_seen=n>0&&n<512;
        }
        free(raw);
    }
    valid=valid && entry_seen && count>0 && ffr3_text(&buffer,"]}") && ffr3_budget(&p->stop);free(j);free(capture);free(inventory);
    if(!valid){free(buffer.bytes);return NULL;}*length=buffer.used;return buffer.bytes;
}

static const char *ffr3_pin_bootstrap =
    "import os,sys,time,struct,select,json,hashlib,types,importlib.abc,importlib.util\n"
    "origin,stop=int(sys.argv[1]),int(sys.argv[2])\n"
    "def check():\n"
    "    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)\n"
    "    if stop!=origin+15000000000 or not origin<=now<stop:raise RuntimeError('NATIVE_PIN_BUDGET')\n"
    "def read_exact(size):\n"
    "    result=bytearray()\n"
    "    while len(result)<size:\n"
    "        check();poll=select.poll();poll.register(0,select.POLLIN|select.POLLHUP|select.POLLERR)\n"
    "        if not poll.poll(max(1,(stop-time.clock_gettime_ns(time.CLOCK_MONOTONIC)+999999)//1000000)):continue\n"
    "        try:part=os.read(0,min(65536,size-len(result)))\n"
    "        except (InterruptedError,BlockingIOError):continue\n"
    "        if not part:raise RuntimeError('NATIVE_PIN_TRUNCATED')\n"
    "        result.extend(part)\n"
    "    check();return bytes(result)\n"
    "length=struct.unpack('!I',read_exact(4))[0]\n"
    "if not 1<=length<=67108864:raise RuntimeError('NATIVE_PIN_BOUND')\n"
    "raw=read_exact(length)\n"
    "def pairs(rows):\n"
    "    result={}\n"
    "    for key,value in rows:\n"
    "        if key in result:raise RuntimeError('NATIVE_PIN_DUPLICATE')\n"
    "        result[key]=value\n"
    "    return result\n"
    "frame=json.loads(raw,object_pairs_hook=pairs)\n"
    "if json.dumps(frame,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()!=raw or set(frame)!={'inventory','plan','plan_hash','sources'}:raise RuntimeError('NATIVE_PIN_CANONICAL')\n"
    "plan=frame['plan'];planraw=json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()\n"
    "if hashlib.sha256(planraw).hexdigest()!=frame['plan_hash'] or set(plan)!={'schema','identity','source_inventory','modules','qualification'} or plan['schema']!='KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0':raise RuntimeError('NATIVE_PIN_PLAN')\n"
    "inventory=frame['inventory'];inventory_raw=json.dumps(inventory,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()\n"
    "if type(inventory) is not list or not 1<=len(inventory)<=4096 or any(type(row) is not list or len(row)!=2 or any(type(value) is not str for value in row) for row in inventory):raise RuntimeError('NATIVE_PIN_INVENTORY')\n"
    "if hashlib.sha256(inventory_raw).hexdigest()!=plan['source_inventory']['hash'] or str(len(inventory_raw))!=plan['source_inventory']['bytes']:raise RuntimeError('NATIVE_PIN_INVENTORY_HASH')\n"
    "expected=dict(inventory)\n"
    "if len(expected)!=len(inventory) or list(expected)!=sorted(expected):raise RuntimeError('NATIVE_PIN_MODULES')\n"
    "planned={row['name']:row['digest'] for row in plan['modules']}\n"
    "if len(planned)!=len(plan['modules']) or list(planned)!=sorted(planned) or any(expected.get(name)!=digest for name,digest in planned.items()):raise RuntimeError('NATIVE_PIN_PLAN_SOURCE')\n"
    "sources={}\n"
    "for row in frame['sources']:\n"
    "    check()\n"
    "    if set(row)!={'name','package','path','payload'} or type(row['package']) is not bool or row['name'] in sources:raise RuntimeError('NATIVE_PIN_SOURCE')\n"
    "    payload=bytes.fromhex(row['payload'])\n"
    "    if expected.get(row['name'])!=hashlib.sha256(payload).hexdigest():raise RuntimeError('NATIVE_PIN_SOURCE_HASH')\n"
    "    sources[row['name']]=(payload,row['package'],row['path'])\n"
    "if set(sources)!=set(expected) or 'tools.failed_fenced_launcher' not in sources:raise RuntimeError('NATIVE_PIN_SOURCE_ROSTER')\n"
    "capsule=types.ModuleType('_kronos_native_bootstrap')\n"
    "capsule.script_hash=hashlib.sha256(sys.orig_argv[sys.orig_argv.index(\"-c\")+1].encode()).hexdigest()\n"
    "capsule.plan_hash=frame['plan_hash'];capsule.sources=tuple((name,sources[name]) for name in sorted(sources))\n"
    "constructed={}\n"
    "class PinnedLoader(importlib.abc.Loader):\n"
    "    def __init__(self,name):\n"
    "        if name not in sources or name in constructed:raise RuntimeError('NATIVE_PIN_LOADER_REPLAY')\n"
    "        self.name=name;self._kronos_native_pinned_payload=sources[name][0];self._kronos_native_plan_hash=frame['plan_hash']\n"
    "        self.code=compile(self._kronos_native_pinned_payload,sources[name][2],'exec',dont_inherit=True)\n"
    "        constructed[name]=self\n"
    "    def create_module(self,spec):return None\n"
    "    def exec_module(self,module):\n"
    "        if module.__spec__.loader is not self or self.name!=module.__spec__.name:raise RuntimeError('NATIVE_PIN_LOADER_CHANGED')\n"
    "        module.__file__=sources[self.name][2];exec(self.code,module.__dict__)\n"
    "    def is_package(self,name):return sources[name][1]\n"
    "class PinnedFinder(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self,name,path=None,target=None):\n"
    "        if name in sources:return importlib.util.spec_from_loader(name,PinnedLoader(name),is_package=sources[name][1])\n"
    "        if name in {'tools','tools.macos'} and name not in sources and any(key.startswith(name+'.') for key in sources):\n"
    "            specification=importlib.util.spec_from_loader(name,loader=None,is_package=True)\n"
    "            specification.submodule_search_locations=[];return specification\n"
    "        if name in {'tools','kronos'} or name.startswith(('tools.','kronos.')):raise ImportError('NATIVE_PIN_UNCAPTURED_MODULE')\n"
    "capsule.loader_type=PinnedLoader;capsule.constructed=constructed;capsule.finder=PinnedFinder()\n"
    "sys.modules[capsule.__name__]=capsule;sys.meta_path.insert(0,capsule.finder)\n"
    "check()\n"
    "from tools import failed_fenced_launcher as entry\n"
    "raise SystemExit(entry.native_helper_main(origin_ns=origin,stop_deadline_ns=stop))\n"
    ;


static BackendStartResult __attribute__((unused)) monitor_failed_fenced_start(
    pid_t child, const struct timespec *deadline, const BackendStartMonitor *monitor
) {
    if (!deadline || !monitor || !monitor->monotonic_now || !monitor->observe_child ||
        !monitor->ready || !monitor->pause) return BACKEND_START_INTERNAL_FAILURE;
    for (;;) {
        int status=0; errno=0;
        pid_t observed=monitor->observe_child(child,&status);
        if(observed==child)return BACKEND_START_CHILD_EXITED;
        if(observed!=0 && !(observed<0 && errno==EINTR))return BACKEND_START_INTERNAL_FAILURE;
        struct timespec now;
        if(monitor->monotonic_now(&now)!=0)return BACKEND_START_INTERNAL_FAILURE;
        if(time_reached(&now,deadline))return BACKEND_START_READY_TIMEOUT;
        if(monitor->ready()){
            if(monitor->monotonic_now(&now)!=0)return BACKEND_START_INTERNAL_FAILURE;
            return time_reached(&now,deadline) ? BACKEND_START_READY_TIMEOUT : BACKEND_START_READY;
        }
        struct timespec duration=time_until(&now,deadline),remaining;
        if(monitor->pause(&duration,&remaining)!=0 && errno!=EINTR)return BACKEND_START_INTERNAL_FAILURE;
    }
}

/* A private inherited pipe is a native capability.  These transport primitives
 * do not treat a path, file, token or environment value as a grant. */
static int __attribute__((unused)) failed_fenced_pipe(int descriptors[2]) {
    if(pipe(descriptors)!=0)return 0;
    for(int i=0;i<2;i++){
        int flags=fcntl(descriptors[i],F_GETFD);
        int status=fcntl(descriptors[i],F_GETFL);
        if(flags<0 || status<0 || fcntl(descriptors[i],F_SETFD,flags|FD_CLOEXEC)<0 ||
           fcntl(descriptors[i],F_SETFL,status|O_NONBLOCK)<0){
            close(descriptors[0]);close(descriptors[1]);return 0;
        }
    }
    return 1;
}

static int __attribute__((unused)) failed_fenced_child_descriptor(int reader,int writer) {
    struct stat info;
    if(reader<0 || writer<0 || reader==writer || fstat(reader,&info)!=0 || !S_ISFIFO(info.st_mode))return 0;
    if(close(writer)!=0)return 0;
    if(reader!=3){if(dup2(reader,3)!=3)return 0;close(reader);}
    int flags=fcntl(3,F_GETFD);
    /* The one deliberate inherited endpoint survives exec, and the Python
     * bootstrap immediately restores CLOEXEC before its first helper. */
    if(flags<0 || fcntl(3,F_SETFD,flags&~FD_CLOEXEC)<0)return 0;
    int maximum=getdtablesize();
    if(maximum<4)return 0;
    for(int descriptor=4;descriptor<maximum;descriptor++){
        if(close(descriptor)!=0 && errno!=EBADF)return 0;
    }
    return 1;
}

static int __attribute__((unused)) failed_fenced_send_frame(
    int writer,const unsigned char *bytes,size_t length,const struct timespec *stop_deadline
) {
    int ok=0;struct stat info;struct sigaction ignore={0},previous={0};int signal_changed=0;
    if(writer<0)return 0;
    if(!bytes || length<1 || length>8192 || !stop_deadline ||
       fstat(writer,&info)!=0 || !S_ISFIFO(info.st_mode))goto done;
    ignore.sa_handler=SIG_IGN;
    if(sigaction(SIGPIPE,&ignore,&previous)!=0)goto done;
    signal_changed=1;
    unsigned char frame[8196];uint32_t size=htonl((uint32_t)length);
    memcpy(frame,&size,4);memcpy(frame+4,bytes,length);
    size_t offset=0;
    while(offset<length+4){
        if(!recovery_wait_io(writer,POLLOUT,stop_deadline))goto done;
        ssize_t wrote=write(writer,frame+offset,length+4-offset);
        if(wrote<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK))continue;
        if(wrote<=0)goto done;
        offset+=(size_t)wrote;
        struct timespec now;
        if(clock_gettime(CLOCK_MONOTONIC,&now)!=0 || time_reached(&now,stop_deadline))goto done;
    }
    ok=1;
done:
    close(writer); /* exactly one frame and EOF, including every denial */
    if(signal_changed)(void)sigaction(SIGPIPE,&previous,NULL);
    return ok;
}

/* Anonymous, one-call helper transport. It never passes a role key or control
 * checkpoint. No helper output is a signed proof or a composition authority. */
static int ffr3_helper_write(int fd,const char *bytes,size_t length,const struct timespec *stop) {
    size_t offset=0;
    while(offset<length){
        if(!recovery_wait_io(fd,POLLOUT,stop))return 0;
        ssize_t size=write(fd,bytes+offset,length-offset);
        if(size<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK))continue;
        if(size<=0)return 0;offset+=(size_t)size;
    }
    return ffr3_budget(stop);
}
static int ffr3_helper_frame(int fd,const char *bytes,size_t length,size_t maximum,const struct timespec *stop) {
    if(!bytes || !length || length>maximum || length>UINT32_MAX)return 0;
    uint32_t size=htonl((uint32_t)length);
    return ffr3_helper_write(fd,(const char*)&size,4,stop) && ffr3_helper_write(fd,bytes,length,stop);
}
static int ffr3_helper_read(int fd,char *bytes,size_t length,const struct timespec *stop) {
    size_t offset=0;
    while(offset<length){
        if(!recovery_wait_io(fd,POLLIN,stop))return 0;
        ssize_t size=read(fd,bytes+offset,length-offset);
        if(size<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK))continue;
        if(size<=0)return 0;offset+=(size_t)size;
    }
    return ffr3_budget(stop);
}
static int ffr3_helper_context(const char *raw,pid_t helper,char **changed) {
    RecoveryJson *parsed=calloc(1,sizeof(*parsed));if(!parsed)return 0;
    int valid=ffr3_canonical_object(parsed,raw),field=recovery_json_get(parsed,0,"helper");
    struct proc_bsdinfo info;memset(&info,0,sizeof(info));
    if(valid)valid=field>=0 && proc_pidinfo(helper,PROC_PIDTBSDINFO,0,&info,sizeof(info))==(int)sizeof(info) && info.pbi_pid==(uint32_t)helper;
    if(!valid){free(parsed);return 0;}
    char process[1024],runtime_input[256],runtime[65];unsigned char digest[32];
    int n=snprintf(runtime_input,sizeof(runtime_input),"R3-native-helper/%ld/%llu/%llu",(long)helper,
        (unsigned long long)info.pbi_start_tvsec,(unsigned long long)info.pbi_start_tvusec);
    if(n<1 || (size_t)n>=sizeof(runtime_input)){free(parsed);return 0;}
    CC_SHA256(runtime_input,(CC_LONG)n,digest);ffr3_hex(digest,runtime);
    n=snprintf(process,sizeof(process),"{\"kernel_birth\":{\"microseconds\":\"%llu\",\"seconds\":\"%llu\"},\"pid\":\"%ld\",\"runtime\":\"%s\"}",
        (unsigned long long)info.pbi_start_tvusec,(unsigned long long)info.pbi_start_tvsec,(long)helper,runtime);
    if(n<1 || (size_t)n>=sizeof(process)){free(parsed);return 0;}
    size_t before=ffr3_token_start(parsed,field),after=ffr3_token_end(parsed,field),capacity=strlen(raw)+sizeof(process)+1;
    char *result=malloc(capacity);if(!result){free(parsed);return 0;}
    n=snprintf(result,capacity,"%.*s%s%s",(int)before,raw,process,raw+after);free(parsed);
    if(n<1 || (size_t)n>=capacity){free(result);return 0;}
    *changed=result;return 1;
}
typedef struct FFR3HelperCall {
    const char *python,*pin_frame,*context;
    size_t pin_bytes;
    unsigned long long origin_ns,stop_ns;
    struct timespec stop;
    pid_t child;
    int dispatched,joined;
} FFR3HelperCall;
static int __attribute__((unused)) ffr3_run_semantic_helper(FFR3HelperCall *call,char **result,size_t *result_length) {
    if(!call || !result || !result_length || !call->python || !call->pin_frame || !call->context || call->dispatched ||
       call->stop_ns!=call->origin_ns+15000000000ULL || !ffr3_budget(&call->stop))return 0;
    RecoveryJson *parsed=calloc(1,sizeof(*parsed));if(!parsed)return 0;
    int valid=ffr3_canonical_object(parsed,call->context);free(parsed);
    if(!valid || !call->pin_bytes || call->pin_bytes>64U*1024U*1024U)return 0;
    int input[2],output[2];
    if(!failed_fenced_pipe(input))return 0;
    if(!failed_fenced_pipe(output)){close(input[0]);close(input[1]);return 0;}
    char origin[32],stop[32];snprintf(origin,sizeof(origin),"%llu",call->origin_ns);snprintf(stop,sizeof(stop),"%llu",call->stop_ns);
    /* The caller must have durably registered this exact invocation before
     * entering. The native call itself can never be retried after dispatch. */
    call->dispatched=1;pid_t child=fork();call->child=child;
    if(child<0){close(input[0]);close(input[1]);close(output[0]);close(output[1]);return 0;}
    if(child==0){
        if(dup2(input[0],0)!=0 || dup2(output[1],1)!=1)_exit(91);
        int null=open("/dev/null",O_WRONLY);if(null<0 || dup2(null,2)!=2)_exit(92);
        int maximum=getdtablesize();if(maximum<3)_exit(93);
        for(int descriptor=3;descriptor<maximum;descriptor++)if(close(descriptor)!=0 && errno!=EBADF)_exit(94);
        if(!ffr3_set_native_home())_exit(94);
        execl(call->python,call->python,"-I","-B","-S","-c",ffr3_pin_bootstrap,origin,stop,(char*)NULL);_exit(95);
    }
    close(input[0]);close(output[1]);
    struct sigaction ignore={0},previous={0};ignore.sa_handler=SIG_IGN;
    int signal_changed=sigaction(SIGPIPE,&ignore,&previous)==0;valid=signal_changed;
    char *context=NULL;
    if(valid)valid=ffr3_helper_context(call->context,child,&context) &&
        ffr3_helper_frame(input[1],call->pin_frame,call->pin_bytes,64U*1024U*1024U,&call->stop) &&
        ffr3_helper_frame(input[1],context,strlen(context),FFR3_MAX_RECORD,&call->stop);
    free(context);close(input[1]);
    if(signal_changed)(void)sigaction(SIGPIPE,&previous,NULL);
    uint32_t encoded=0;char *raw=NULL;size_t length=0;
    if(valid)valid=ffr3_helper_read(output[0],(char*)&encoded,4,&call->stop);
    if(valid){length=ntohl(encoded);valid=length>0 && length<=FFR3_MAX_RECORD;}
    if(valid){raw=malloc(length+1);valid=raw!=NULL && ffr3_helper_read(output[0],raw,length,&call->stop);}
    if(valid){
        char extra;valid=recovery_wait_io(output[0],POLLIN,&call->stop) && read(output[0],&extra,1)==0;
        raw[length]=0;
    }
    close(output[0]);int status=0;pid_t observed;
    /* Preserve ownership through an actual late return; never kill, abandon,
     * retry or count a late result as valid. */
    do{observed=waitpid(child,&status,0);}while(observed<0 && errno==EINTR);
    call->joined=observed==child;
    valid=valid && call->joined && WIFEXITED(status) && WEXITSTATUS(status)==0 && ffr3_budget(&call->stop);
    if(valid){parsed=calloc(1,sizeof(*parsed));valid=parsed && ffr3_canonical_object(parsed,raw);free(parsed);}
    if(!valid){free(raw);return 0;}
    *result=raw;*result_length=length;return 1;
}

/* The native session is the sole L issuer. Private helper calls have one
 * monotone sequence and one exact parent/pipe/source context. */
static char *ffr3_format(const char *format,...) {
    va_list args,copy;va_start(args,format);va_copy(copy,args);
    int length=vsnprintf(NULL,0,format,args);va_end(args);
    if(length<0 || (unsigned)length>4U*FFR3_MAX_RECORD){va_end(copy);return NULL;}
    char *raw=malloc((size_t)length+1);if(raw)vsnprintf(raw,(size_t)length+1,format,copy);va_end(copy);return raw;
}
static char *ffr3_bytes_hex(const char *raw,size_t length) {
    if(length>FFR3_MAX_RECORD)return NULL;char *hex=malloc(length*2+1);if(!hex)return NULL;
    const char *digits="0123456789abcdef";for(size_t i=0;i<length;i++){unsigned char c=(unsigned char)raw[i];hex[i*2]=digits[c>>4];hex[i*2+1]=digits[c&15];}hex[length*2]=0;return hex;
}
static char *ffr3_unhex(const char *hex,size_t *length) {
    size_t size=strlen(hex);if(!size || size%2 || size>2*FFR3_MAX_RECORD)return NULL;
    char *raw=malloc(size/2+1);if(!raw)return NULL;const char *digits="0123456789abcdef";
    for(size_t i=0;i<size;i+=2){const char *a=strchr(digits,hex[i]),*b=strchr(digits,hex[i+1]);if(!a||!b){free(raw);return NULL;}raw[i/2]=(char)(((a-digits)<<4)|(b-digits));}
    raw[size/2]=0;if(memchr(raw,0,size/2)){free(raw);return NULL;}*length=size/2;return raw;
}
static char *ffr3_blob_ref(const char *identity,const char *raw) {
    if(!ffr3_id(identity)||!raw)return NULL;unsigned char bytes[32];char hash[65];size_t length=strlen(raw);
    CC_SHA256(raw,(CC_LONG)length,bytes);ffr3_hex(bytes,hash);
    return ffr3_format("{\"bytes\":\"%zu\",\"hash\":\"%s\",\"identity\":\"%s\"}",length,hash,identity);
}
static char *ffr3_proof_blob(const char *raw) {
    char *payload=ffr3_json_field(raw,"payload");char identity[256];
    char *ref=payload && ffr3_json_string_value(payload,"identity",identity,sizeof(identity))?ffr3_blob_ref(identity,raw):NULL;free(payload);return ref;
}
static char *ffr3_evidence(const char *raw) {
    char kind[96],identity[256];char *payload=ffr3_json_field(raw,"payload");
    if(!payload||!ffr3_json_string_value(raw,"kind",kind,sizeof(kind))||!ffr3_json_string_value(payload,"identity",identity,sizeof(identity))){free(payload);return NULL;}free(payload);
    unsigned char bytes[32];char hash[65];CC_SHA256(raw,(CC_LONG)strlen(raw),bytes);ffr3_hex(bytes,hash);
    return ffr3_format("{\"authority\":\"LAUNCHER\",\"bytes\":\"%zu\",\"contract\":\"KRONOS-FAILED-FENCED-EXTERNAL-PROOF:1.0.0:%s\",\"hash\":\"%s\",\"identity\":\"%s\"}",strlen(raw),kind,hash,identity);
}
static char *ffr3_signed_publish(FFR3PreparedNative *p,const FFR3NativeCodec *codec,const char *kind,int external,const char *payload,unsigned long long when) {
    char *raw=malloc(FFR3_MAX_RECORD+1);char digest[65];if(!raw)return NULL;
    if(!ffr3_budget(&p->stop)||!ffr3_native_encode(codec,kind,external,payload,when,raw,FFR3_MAX_RECORD+1)||
       !ffr3_publish_record(external?p->blobs:p->records,codec,raw,kind,external,&p->stop,digest)){free(raw);return NULL;}return raw;
}
static char *ffr3_array_refs(char *const *rows,size_t count) {
    FFR3Buffer buffer={0};if(!ffr3_text(&buffer,"["))return NULL;
    for(size_t i=0;i<count;i++)if((i&&!ffr3_text(&buffer,","))||!ffr3_text(&buffer,rows[i])){free(buffer.bytes);return NULL;}
    if(!ffr3_text(&buffer,"]")){free(buffer.bytes);return NULL;}return buffer.bytes;
}
static char *ffr3_preparation_assertion(const FFR3PreparedNative *p) {
    char *service=ffr3_json_field(p->pin,"service"),*installation=ffr3_json_field(p->pin,"installation"),*catalogue=ffr3_json_field(p->pin,"catalogue"),
      *pin=ffr3_json_field(p->approval,"pin"),*approval=ffr3_blob_ref("native-preparation-approval",p->approval);
    RecoveryJson *j=calloc(1,sizeof(*j));char *refs[4096]={0};size_t used=0;int valid=j&&ffr3_canonical_object(j,p->catalogue);
    int rows=valid?recovery_json_get(j,0,"rows"):-1;
    if(rows<0)valid=0;
    for(int item=rows+1;valid&&item<j->token[rows].next;item=j->token[item].next){
        char *ref=ffr3_json_value(j,recovery_json_get(j,item,"attribution"));if(!ref||used==4096){free(ref);valid=0;break;}
        int duplicate=0;for(size_t i=0;i<used;i++)if(!strcmp(refs[i],ref))duplicate=1;
        if(duplicate)free(ref);else refs[used++]=ref;
    }
    char *decisions=valid?ffr3_array_refs(refs,used):NULL;
    char *result=service&&installation&&catalogue&&pin&&approval&&decisions?ffr3_format("{\"anchors\":{\"approval\":%s,\"catalogue\":%s,\"decisions\":%s,\"pin\":%s},\"attempt\":%s,\"installation\":%s,\"lineage\":%s,\"mode\":%s,\"service\":%s}",approval,catalogue,decisions,pin,p->attempt,installation,p->lineage,p->mode,service):NULL;
    for(size_t i=0;i<used;i++)free(refs[i]);free(j);free(service);free(installation);free(catalogue);free(pin);free(approval);free(decisions);return result;
}
typedef struct FFR3Session {
    FFR3PreparedNative *prepared;FFR3NativeCodec codec;char *capability,*capability_ref,*admissions[32],*dispatches[32];
    char *admission,*dispatch,*control,*helper_process,*fact_refs[4];size_t control_bytes,count,fact_count;unsigned long long sequence;
    char context_hash[65];pid_t helper;int helper_joined,shutdown_sent,original_reserved,claim_reserved,guard_reserved,intent_reserved;
    int fork_spent,grant_spent,done,read_only;char slot[65],nonce[65];pid_t product;int grant_writer;struct timespec ready_deadline;
    char *ack,*intent,*started,*child_process,*ready_payload,*ready_receipt;unsigned long long ack_received_ns,fork_enter_ns,fork_return_ns;
} FFR3Session;
static char *ffr3_admission(FFR3Session *s,const char *operation,const char *action,const char *inputs,unsigned long long accepted) {
    if(s->count>=32||strcmp(s->prepared->mode,"\"ORIGINAL\""))return NULL;
    char *previous=s->count?s->admissions[s->count-1]:"null";
    char *payload=ffr3_format("{\"accepted_ns\":\"%llu\",\"action\":\"%s\",\"attempt\":%s,\"controller\":%s,\"executor\":\"native-controller\",\"identity\":\"%s-admission\",\"inputs\":%s,\"lineage\":%s,\"operation\":\"%s\",\"previous\":%s,\"sequence\":\"%zu\"}",accepted,action,s->prepared->attempt,s->prepared->controller,operation,inputs,s->prepared->lineage,operation,previous,s->count);
    char *raw=payload?ffr3_signed_publish(s->prepared,&s->codec,"CONTROLLER_ADMISSION",1,payload,accepted):NULL;free(payload);
    if(!raw)return NULL;char *ref=ffr3_proof_blob(raw);free(raw);if(!ref)return NULL;
    s->admissions[s->count]=ref;s->admission=ref;s->dispatch=NULL;s->count++;return ref;
}
static char *ffr3_dispatch(FFR3Session *s,const char *state,const char *helper,const char *outputs,unsigned long long started,unsigned long long completed,int success) {
    if(!s->admission)return NULL;char start[40]="null",complete[40]="null";
    if(started)snprintf(start,sizeof(start),"\"%llu\"",started);if(completed)snprintf(complete,sizeof(complete),"\"%llu\"",completed);
    char *payload=ffr3_format("{\"admission\":%s,\"attempt\":%s,\"completed_ns\":%s,\"controller\":%s,\"helper\":%s,\"identity\":\"native-dispatch-%zu-%s\",\"lineage\":%s,\"outcome\":\"%s\",\"outputs\":%s,\"outstanding\":\"%s\",\"previous\":%s,\"started_ns\":%s,\"state\":\"%s\"}",s->admission,s->prepared->attempt,complete,s->prepared->controller,helper?helper:"null",s->count,state,s->prepared->lineage,completed?(helper?(success?"JOINED_SUCCESS":"JOINED_FAILURE"):"RETURNED"):"NONE",outputs,!strcmp(state,"DISPATCHED")?"1":"0",s->dispatch?s->dispatch:"null",start,state);
    char *raw=payload?ffr3_signed_publish(s->prepared,&s->codec,"CONTROLLER_DISPATCH",1,payload,ffr3_now_ns()):NULL;free(payload);
    if(!raw)return NULL;char *ref=ffr3_proof_blob(raw);free(raw);if(!ref)return NULL;
    /* Earlier chain entries remain immutable; only the in-memory head moves. */
    s->dispatch=ref;s->dispatches[s->count-1]=ref;return ref;
}
static char *ffr3_original_preparation_assertion(const FFR3PreparedNative *p);
static char *ffr3_session_context(FFR3Session *s,const char *stage,const char *entry) {
    FFR3PreparedNative *p=s->prepared;char *preparation=ffr3_preparation_assertion(p);char *previous=!strcmp(p->mode,"\"RECOVERY\"")?ffr3_original_preparation_assertion(p):NULL;char *preparations=preparation?(!strcmp(p->mode,"\"ORIGINAL\"")?ffr3_format("[%s]",preparation):(previous?ffr3_format("[%s,%s]",previous,preparation):NULL)):NULL;free(preparation);free(previous);
    char *cap_hash=s->capability_ref?ffr3_json_field(s->capability_ref,"hash"):NULL;unsigned long long origin=(unsigned long long)p->origin.tv_sec*1000000000ULL+(unsigned long long)p->origin.tv_nsec;
    const char *action=!strcmp(stage,"GUARD_ADMISSION")?"VERIFY_STATUS":"AUTHORIZE";
    if(s->read_only){
        char *context=preparations?ffr3_format("{\"action\":\"VERIFY_STATUS\",\"admission\":null,\"authenticated\":[],\"broker\":true,\"clock\":%s,\"control_pid\":null,\"controller\":%s,\"controller_capability\":null,\"custody\":null,\"dispatch\":null,\"helper\":%s,\"helper_entry\":%s,\"helper_plan\":%s,\"key_id\":null,\"operation\":\"installation.guard\",\"origin_ns\":\"%llu\",\"preparations\":%s,\"stage\":\"GUARD_ADMISSION\",\"stop_deadline_ns\":\"%llu\"}",p->clock,p->controller,p->controller,entry,p->helper_plan_blob,origin,preparations,origin+15000000000ULL):NULL;
        free(preparations);free(cap_hash);return context;
    }

    char *context=preparations&&cap_hash?ffr3_format("{\"action\":\"%s\",\"admission\":%s,\"authenticated\":[{\"bytes\":\"%zu\",\"external\":true,\"hash\":%s,\"kind\":\"CONTROLLER_CAPABILITY\"}],\"broker\":true,\"clock\":%s,\"control_pid\":\"%ld\",\"controller\":%s,\"controller_capability\":%s,\"custody\":{\"control_pid\":\"%ld\",\"key_id\":\"%s\",\"retained_control_bytes\":\"%zu\",\"retained_control_hash\":\"%s\",\"verified_ns\":\"%llu\"},\"dispatch\":%s,\"helper\":%s,\"helper_entry\":%s,\"helper_plan\":%s,\"key_id\":\"%s\",\"operation\":\"original.authorize\",\"origin_ns\":\"%llu\",\"preparations\":%s,\"stage\":\"%s\",\"stop_deadline_ns\":\"%llu\"}",action,s->admission?s->admission:"null",strlen(s->capability),cap_hash,p->clock,(long)s->codec.predecessor,p->controller,s->capability_ref,(long)s->codec.predecessor,s->codec.key_id,s->control_bytes,s->codec.key_id,ffr3_now_ns(),s->dispatch?s->dispatch:"null",p->controller,entry,p->helper_plan_blob,s->codec.key_id,origin,preparations,stage,origin+15000000000ULL):NULL;
    free(preparations);free(cap_hash);return context;
}
static char *ffr3_read_frame(int fd,size_t maximum,const struct timespec *stop) {
    uint32_t encoded=0;if(!ffr3_helper_read(fd,(char*)&encoded,4,stop))return NULL;size_t length=ntohl(encoded);
    if(!length||length>maximum)return NULL;char *raw=malloc(length+1);if(!raw)return NULL;
    if(!ffr3_helper_read(fd,raw,length,stop)){free(raw);return NULL;}raw[length]=0;return raw;
}
static int ffr3_canonical_boolean(const RecoveryJson *j,int token,int *value) {
    if(token<0||j->token[token].kind!='v')return 0;
    size_t length=(size_t)(j->token[token].end-j->token[token].start);const char *raw=j->text+j->token[token].start;
    if(length==4&&!memcmp(raw,"true",4)){*value=1;return 1;}if(length==5&&!memcmp(raw,"false",5)){*value=0;return 1;}return 0;
}
static const struct timespec *ffr3_session_deadline(const FFR3Session *s);
static int ffr3_historical_control_binding(const char *raw,const char *control,size_t bytes,const FFR3NativeCodec *codec) {
    char *payload=ffr3_json_field(raw,"payload"),*process=payload?ffr3_json_field(payload,"process"):NULL,
        *live=payload?ffr3_json_field(payload,"live_control"):NULL,*retained=payload?ffr3_json_field(payload,"retained_control"):NULL;
    char pid[32],actual[32],hash[65],count[32],boot[128],expected_boot[128];snprintf(actual,sizeof(actual),"%ld",(long)codec->predecessor);
    int valid=payload&&process&&live&&retained&&ffr3_json_string_value(process,"pid",pid,sizeof(pid))&&!strcmp(pid,actual)&&
        ffr3_json_string_value(payload,"schema",boot,sizeof(boot))&&!strcmp(boot,"KRONOS_BROWSER_BACKEND_CONTROL_V1")&&
        ffr3_json_string_value(payload,"boot_id",boot,sizeof(boot))&&ffr3_json_string_value(codec->clock,"boot_id",expected_boot,sizeof(expected_boot))&&!strcmp(boot,expected_boot);
    const char *refs[]={live,retained};snprintf(actual,sizeof(actual),"%zu",bytes);
    for(size_t i=0;valid&&i<2;i++)valid=ffr3_json_string_value(refs[i],"hash",hash,sizeof(hash))&&!strcmp(hash,codec->key_id)&&
        ffr3_json_string_value(refs[i],"bytes",count,sizeof(count))&&!strcmp(count,actual);
    unsigned char digest[32];if(valid){CC_SHA256(control,(CC_LONG)bytes,digest);ffr3_hex(digest,hash);valid=!strcmp(hash,codec->key_id);}
    free(payload);free(process);free(live);free(retained);return valid;
}
static char *ffr3_broker_verify(FFR3Session *s,const char *payload) {
    RecoveryJson *j=calloc(1,sizeof(*j));char *hex=NULL,*raw=NULL,*result=NULL,*clock=NULL,*control=NULL;size_t length=0,control_bytes=0;int external=0;
    FFR3NativeCodec historical;memset(&historical,0,sizeof(historical));const FFR3NativeCodec *codec=&s->codec;
    if(!j||!ffr3_private_call_object(j,payload)||j->token[0].count!=2||!ffr3_canonical_boolean(j,recovery_json_get(j,0,"external"),&external))goto done;
    int token=recovery_json_get(j,0,"raw");if(token<0||j->token[token].kind!='s')goto done;
    size_t n=(size_t)(j->token[token].end-j->token[token].start);hex=malloc(n+1);if(!hex)goto done;memcpy(hex,j->text+j->token[token].start,n);hex[n]=0;
    raw=ffr3_unhex(hex,&length);if(!raw)goto done;
    char kind[96],key[65],hash[65];unsigned char digest[32];
    if(!ffr3_json_string_value(raw,"kind",kind,sizeof(kind))||!ffr3_json_string_value(raw,"key_id",key,sizeof(key))||!valid_token(key))goto done;
    clock=ffr3_json_field(raw,"clock");if(!clock)goto done;
    /* Historical guards retain their own exact control/boot. Current custody
     * is never substituted, and no key/control byte leaves this native call. */
    if(s->read_only||strcmp(key,s->codec.key_id)||strcmp(clock,s->codec.clock)){
        int custody=ffr3_child_directory(s->prepared->root,"custody");char name[96];snprintf(name,sizeof(name),"%s.control",key);
        control=custody>=0?ffr3_capture_at(custody,name,255,&control_bytes,1,ffr3_session_deadline(s)):NULL;if(custody>=0)close(custody);
        if(!control||!ffr3_native_codec_init(&historical,control,clock,s->prepared->controller)||strcmp(historical.key_id,key))goto done;
        codec=&historical;
        CC_SHA256(raw,(CC_LONG)length,digest);ffr3_hex(digest,hash);
        char retained_name[180];if(external)snprintf(retained_name,sizeof(retained_name),"%s.blob",hash);else snprintf(retained_name,sizeof(retained_name),"%s-%s.json",kind,hash);
        size_t retained_bytes=0;char *retained=NULL;
        const char *fixed=!strcmp(kind,"GUARD")?"guard":!strcmp(kind,"CLAIM")?"claim":!strcmp(kind,"CHILD_INTENT")?"child-intent":!strcmp(kind,"CHILD_IDENTITY")?"child-identity":!strcmp(kind,"CONSUMPTION")?"consumption":NULL;
        if(!external&&fixed){char *body=ffr3_json_field(raw,"payload");char slot[65];
            int area=-1,slotfd=-1;if(body&&ffr3_json_string_value(body,"slot",slot,sizeof(slot))&&valid_token(slot)){
                area=ffr3_child_directory(s->prepared->root,!strcmp(kind,"GUARD")?"guards":"slots");slotfd=area>=0?ffr3_child_directory(area,slot):-1;
                retained=slotfd>=0?ffr3_capture_at(slotfd,fixed,FFR3_MAX_RECORD,&retained_bytes,1,ffr3_session_deadline(s)):NULL;}
            if(slotfd>=0)close(slotfd);if(area>=0)close(area);free(body);
        }else retained=ffr3_capture_at(external?s->prepared->blobs:s->prepared->records,retained_name,FFR3_MAX_RECORD,&retained_bytes,1,ffr3_session_deadline(s));
        int exact=retained&&retained_bytes==length&&!memcmp(retained,raw,length);free(retained);if(!exact)goto done;
    }
    if(!ffr3_native_verify(codec,raw,external))goto done;
    if(external&&!strcmp(kind,"CONTROL_BINDING")){
        if(!control){int custody=ffr3_child_directory(s->prepared->root,"custody");char name[96];snprintf(name,sizeof(name),"%s.control",key);
            control=custody>=0?ffr3_capture_at(custody,name,255,&control_bytes,1,ffr3_session_deadline(s)):NULL;if(custody>=0)close(custody);}
        if(!control||!ffr3_historical_control_binding(raw,control,control_bytes,codec))goto done;
    }
    CC_SHA256(raw,(CC_LONG)length,digest);ffr3_hex(digest,hash);
    result=ffr3_format("{\"bytes\":\"%zu\",\"external\":%s,\"hash\":\"%s\",\"kind\":\"%s\"}",length,external?"true":"false",hash,kind);
 done:if(control){memset(control,0,control_bytes);free(control);}memset(&historical,0,sizeof(historical));free(clock);free(j);free(hex);free(raw);return result;
}

static const struct timespec *ffr3_session_deadline(const FFR3Session *s);
static char *ffr3_scan_proof(FFR3Session *s,const char *kind,const char *identity,const char *subject,int *complete) {
    if(complete)*complete=0;
    /* dup() shares the directory stream offset. A second bounded observation
     * must enumerate the same complete retained namespace independently. */
    DIR *directory=ffr3_directory_stream(s->prepared->blobs);if(!directory)return NULL;struct dirent *entry;char *found=NULL;size_t seen=0,total=0;int valid=1;
    while(valid&&(entry=readdir(directory))){const char *name=entry->d_name;if(!strcmp(name,".")||!strcmp(name,".."))continue;
        if(++seen>4096 || strlen(name)!=69 || strcmp(name+64,".blob")){valid=0;break;}
        size_t length=0;char *raw=ffr3_capture_at(s->prepared->blobs,name,16U*FFR3_MAX_RECORD,&length,1,ffr3_session_deadline(s));
        if(!raw || total+length>64U*1024U*1024U){free(raw);valid=0;break;}total+=length;
        unsigned char digest[32];char hash[65];CC_SHA256(raw,(CC_LONG)length,digest);ffr3_hex(digest,hash);
        if(memcmp(name,hash,64)){free(raw);valid=0;break;}
        if(length>FFR3_MAX_RECORD||memchr(raw,0,length)){free(raw);continue;}
        RecoveryJson *j=calloc(1,sizeof(*j));int candidate=j&&ffr3_canonical_object(j,raw)&&recovery_field(j,0,"kind",kind);
        if(candidate){char *payload=ffr3_json_field(raw,"payload"),*process=payload?ffr3_json_field(payload,"process"):NULL;char value[256];
            candidate=ffr3_native_verify(&s->codec,raw,1) && (!identity||(payload&&ffr3_json_string_value(payload,"identity",value,sizeof(value))&&!strcmp(value,identity))) &&
              (!subject||(process&&!strcmp(subject,process)));
            free(payload);free(process);
            if(candidate&&!strcmp(kind,"EXECUTOR_TERMINATION")){
                char *p=ffr3_json_field(raw,"payload"),*a=p?ffr3_json_field(p,"original_attempt"):NULL,*c=p?ffr3_json_field(p,"original_controller"):NULL;
                candidate=a&&c&&!strcmp(a,s->prepared->attempt)&&!strcmp(c,s->prepared->controller);free(p);free(a);free(c);
            }
            if(candidate){if(found){free(raw);valid=0;break;}found=raw;raw=NULL;}}
        free(j);free(raw);
    }
    closedir(directory);if(!valid){free(found);return NULL;}if(complete)*complete=1;return found;
}
static char *ffr3_find_proof(FFR3Session *s,const char *kind,const char *identity,const char *subject) {
    return ffr3_scan_proof(s,kind,identity,subject,NULL);
}
static int ffr3_process_decimal(const char *text,unsigned long long *value) {
    if(!text||!*text||(text[0]=='0'&&text[1]))return 0;
    for(const char *p=text;*p;p++)if(*p<'0'||*p>'9')return 0;
    errno=0;char *end=NULL;*value=strtoull(text,&end,10);return !errno&&end&&!*end;
}
static int ffr3_observe_process(pid_t pid,unsigned long long seconds,unsigned long long microseconds,int exit_observation,
        const struct timespec *stop,struct proc_bsdinfo *process,int *size,int *error) {
    if(pid<2||microseconds>=1000000ULL||!process||!size||!error)return 0;
    for(;;){
        if(!ffr3_budget(stop))return 0;
        memset(process,0,sizeof(*process));errno=0;
        *size=proc_pidinfo(pid,PROC_PIDTBSDINFO,0,process,sizeof(*process));*error=errno;
        if(!ffr3_budget(stop))return 0;
        if(*size==0&&*error==ESRCH)return exit_observation;
        if(*size!=(int)sizeof(*process)||*error||process->pbi_pid!=(uint32_t)pid)return 0;
        int match=process->pbi_start_tvsec==seconds&&process->pbi_start_tvusec==microseconds;
        if(!exit_observation)return match;
        if(!match)return 1;
        /* ACK precedes the write-free predecessor exit. Observe that same
         * kernel process until it exits, never resending a workflow request
         * or replacing the inherited absolute stop with a polling timeout. */
        struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
        long long remaining=(long long)(stop->tv_sec-now.tv_sec)*1000000000LL+stop->tv_nsec-now.tv_nsec;
        if(remaining<=0)return 0;
        struct timespec pause={0,remaining<10000000LL?(long)remaining:10000000L};
        while(nanosleep(&pause,&pause)!=0){if(errno!=EINTR||!ffr3_budget(stop))return 0;}
    }
}
static char *ffr3_native_process_proof(FFR3Session *s,const char *subject,const char *kind) {
    char pid[32],seconds[32],microseconds[32];char *birth=ffr3_json_field(subject,"kernel_birth");
    if(!birth||!ffr3_json_string_value(subject,"pid",pid,sizeof(pid))||!ffr3_json_string_value(birth,"seconds",seconds,sizeof(seconds))||!ffr3_json_string_value(birth,"microseconds",microseconds,sizeof(microseconds))){free(birth);return NULL;}free(birth);
    if(strcmp(kind,"PROCESS_BIRTH")&&strcmp(kind,"PROCESS_EXIT"))return NULL;
    unsigned long long numeric_pid=0,numeric_seconds=0,numeric_microseconds=0;
    if(!ffr3_process_decimal(pid,&numeric_pid)||numeric_pid<2||numeric_pid>INT_MAX||
       !ffr3_process_decimal(seconds,&numeric_seconds)||!ffr3_process_decimal(microseconds,&numeric_microseconds))return NULL;
    struct proc_bsdinfo process;int size=0,error=0;
    if(!ffr3_observe_process((pid_t)numeric_pid,numeric_seconds,numeric_microseconds,!strcmp(kind,"PROCESS_EXIT"),
        &s->prepared->stop,&process,&size,&error))return NULL;
    int match=size==(int)sizeof(process)&&process.pbi_start_tvsec==numeric_seconds&&process.pbi_start_tvusec==numeric_microseconds;
    char *observed=NULL;if(size==(int)sizeof(process)){
        char *runtime=ffr3_json_field(subject,"runtime");observed=runtime?ffr3_format("{\"kernel_birth\":{\"microseconds\":\"%llu\",\"seconds\":\"%llu\"},\"pid\":\"%u\",\"runtime\":%s}",(unsigned long long)process.pbi_start_tvusec,(unsigned long long)process.pbi_start_tvsec,process.pbi_pid,runtime):NULL;free(runtime);
    }else observed=strdup("null");
    char boot[128];if(!observed||!ffr3_json_string_value(s->prepared->clock,"boot_id",boot,sizeof(boot))){free(observed);return NULL;}
    unsigned long long now=ffr3_now_ns();char *native=ffr3_format("{\"adapter\":\"DARWIN_KERNEL_V1\",\"boot_id\":\"%s\",\"errno\":\"%d\",\"kind\":\"%s\",\"observed_ns\":\"%llu\",\"observed_process\":%s,\"observer\":%s,\"return_bytes\":\"%d\",\"schema\":\"KRONOS_DARWIN_KERNEL_OBSERVATION_V1\",\"subject\":%s,\"syscall\":\"proc_pidinfo:PROC_PIDTBSDINFO\"}",boot,error,kind,now,observed,s->prepared->controller,size,subject);free(observed);
    char identity[256];snprintf(identity,sizeof(identity),"native-%s-%llu",kind,now);char *ref=native?ffr3_blob_ref(identity,native):NULL;
    char hash[65],name[80];int valid=ref&&ffr3_json_string_value(ref,"hash",hash,sizeof(hash));if(valid){snprintf(name,sizeof(name),"%s.blob",hash);valid=ffr3_publish_immutable(s->prepared->blobs,name,native,strlen(native),&s->prepared->stop);}free(native);
    char *payload=valid?ffr3_format("{\"adapter\":\"DARWIN_KERNEL_V1\",\"boot_id\":\"%s\",\"identity\":\"%s-proof\",\"kind\":\"%s\",\"observed_ns\":\"%llu\",\"observer\":%s,\"raw\":%s,\"result\":\"%s\",\"subject\":%s}",boot,identity,kind,now,s->prepared->controller,ref,match?"MATCH":"EXITED",subject):NULL;free(ref);
    char *raw=payload?ffr3_signed_publish(s->prepared,&s->codec,"PLATFORM_OBSERVATION",1,payload,now):NULL;free(payload);return raw;
}
static char *ffr3_unique_approval_binding(FFR3PreparedNative *p,const char *purpose,char **identity) {
    RecoveryJson *j=calloc(1,sizeof(*j));char *binding=NULL;unsigned count=0;
    if(!j||!ffr3_canonical_object(j,p->catalogue)){free(j);return NULL;}int rows=recovery_json_get(j,0,"rows");
    if(rows<0){free(j);return NULL;}
    for(int item=rows+1;item<j->token[rows].next;item=j->token[item].next){
        if(!recovery_field(j,item,"purpose",purpose)||!recovery_field(j,item,"authority","SPONSOR"))continue;
        if(++count!=1)break;binding=ffr3_json_value(j,recovery_json_get(j,item,"bindings"));*identity=ffr3_json_value(j,recovery_json_get(j,item,"identity"));
    }
    free(j);if(count!=1){free(binding);free(*identity);*identity=NULL;return NULL;}return binding;
}
static int ffr3_checkpoint_storage(FFR3Session *s) {
    char name[80];int custody=ffr3_child_directory(s->prepared->root,"custody");if(custody<0)return 0;
    snprintf(name,sizeof(name),"%s.control",s->codec.key_id);struct stat metadata;int valid;
    if(fstatat(custody,name,&metadata,AT_SYMLINK_NOFOLLOW)==0){size_t n=0;char *old=ffr3_capture_at(custody,name,255,&n,1,&s->prepared->stop);valid=old&&n==s->control_bytes&&!memcmp(old,s->control,n);free(old);}
    else valid=errno==ENOENT&&!strcmp(s->prepared->mode,"\"ORIGINAL\"")&&
        ffr3_publish_immutable(custody,name,s->control,s->control_bytes,&s->prepared->stop);
    close(custody);return valid;
}
static int ffr3_retain_control(FFR3Session *s) {
    char *predecessor=ffr3_json_field(s->prepared->lineage,"predecessor");
    char *birth=predecessor?ffr3_json_field(predecessor,"kernel_birth"):NULL;
    char pid[32],seconds[32],microseconds[32],actual[32];struct proc_bsdinfo observed={0};
    snprintf(actual,sizeof(actual),"%ld",(long)s->codec.predecessor);
    int bound=predecessor&&birth&&ffr3_json_string_value(predecessor,"pid",pid,sizeof(pid))&&!strcmp(pid,actual)&&
        proc_pidinfo(s->codec.predecessor,PROC_PIDTBSDINFO,0,&observed,sizeof(observed))==(int)sizeof(observed)&&
        observed.pbi_pid==(uint32_t)s->codec.predecessor;
    if(bound){snprintf(actual,sizeof(actual),"%llu",(unsigned long long)observed.pbi_start_tvsec);
        bound=ffr3_json_string_value(birth,"seconds",seconds,sizeof(seconds))&&!strcmp(seconds,actual);
        snprintf(actual,sizeof(actual),"%llu",(unsigned long long)observed.pbi_start_tvusec);
        bound=bound&&ffr3_json_string_value(birth,"microseconds",microseconds,sizeof(microseconds))&&!strcmp(microseconds,actual);}
    char *approval=NULL,*binding=bound?ffr3_unique_approval_binding(s->prepared,
        !strcmp(s->prepared->mode,"\"ORIGINAL\"")?"ORIGINAL_OPERATION":"RECOVERY_OPERATION",&approval):NULL;
    char *source_ref=binding?ffr3_json_field(binding,!strcmp(s->prepared->mode,"\"ORIGINAL\"")?"source":"predecessor_source"):NULL;
    char *source=source_ref?ffr3_blob_at(s->prepared->blobs,source_ref,"blob",&s->prepared->stop):NULL;
    char *payload=source?ffr3_json_field(source,"payload"):NULL,*process=payload?ffr3_json_field(payload,"process"):NULL;
    char kind[96],role[96];bound=bound&&source&&process&&!strcmp(process,predecessor)&&
        ffr3_native_verify(&s->codec,source,1)&&ffr3_json_string_value(source,"kind",kind,sizeof(kind))&&!strcmp(kind,"SOURCE")&&
        ffr3_json_string_value(source,"role",role,sizeof(role))&&!strcmp(role,"PREDECESSOR");
    free(predecessor);free(birth);free(approval);free(binding);free(source_ref);free(source);free(payload);free(process);
    if(!bound||!ffr3_budget(&s->prepared->stop))return 0;
    int parent=openat(s->prepared->root,"..",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(parent<0)return 0;
    s->control=ffr3_capture_at(parent,"browser-backend-v1.control",255,&s->control_bytes,1,&s->prepared->stop);close(parent);
    if(!s->control)return 0;unsigned char bytes[32];char hash[65];CC_SHA256(s->control,(CC_LONG)s->control_bytes,bytes);ffr3_hex(bytes,hash);
    return !strcmp(hash,s->codec.key_id)&&ffr3_checkpoint_storage(s);
}
static char *ffr3_failed_active_reservation(FFR3Session *s,const char *binding,const char *permission) {
    char attempt[65],generation[65],target[41],path[PATH_MAX],control_path[PATH_MAX];struct passwd *account=getpwuid(geteuid());
    if(!account||!ffr3_json_string_value(binding,"attempt",attempt,sizeof(attempt))||!valid_token(attempt)||
        !ffr3_json_string_value(binding,"generation",generation,sizeof(generation))||!valid_token(generation)||
        snprintf(path,sizeof(path),"%s/Library/Application Support/KRONOS/runtime/failed-active-recovery-v1",account->pw_dir)>=(int)sizeof(path)||
        snprintf(control_path,sizeof(control_path),"%s/Library/Application Support/KRONOS/runtime/browser-backend-v1.control",account->pw_dir)>=(int)sizeof(control_path))return NULL;
    char *permission_raw=ffr3_blob_at(s->prepared->blobs,permission,"blob",&s->prepared->stop);RecoveryJson *j=calloc(1,sizeof(*j));
    int valid=permission_raw&&j&&recovery_json_document(j,permission_raw)&&recovery_string(j,0,"successor_revision",target,sizeof(target));
    RecoveryAuthorization native;memset(&native,0,sizeof(native));long long now=recovery_now_us();
    if(valid)valid=ffr3_budget(&s->prepared->stop)&&recovery_load_authorization(path,attempt,control_path,s->codec.predecessor,target,now,&native);
    if(valid){char hash[65];valid=ffr3_json_string_value(permission,"hash",hash,sizeof(hash))&&!strcmp(hash,native.digest)&&!strcmp(native.maintenance,generation)&&recovery_reserve(&native,generation,now);}
    char raw[1024];int bytes=valid?recovery_attempt_record(&native,generation,now,raw,sizeof(raw)):0;char *ref=NULL;
    if(bytes>0&&bytes<(int)sizeof(raw)){ref=ffr3_blob_ref("native-failed-active-reservation",raw);char hash[65],name[80];valid=ref&&ffr3_json_string_value(ref,"hash",hash,sizeof(hash));
        if(valid){snprintf(name,sizeof(name),"%s.blob",hash);valid=ffr3_publish_immutable(s->prepared->blobs,name,raw,(size_t)bytes,&s->prepared->stop);}if(!valid){free(ref);ref=NULL;}}
    free(j);free(permission_raw);return ref;
}
static char *ffr3_original_prepare(FFR3Session *s) {
    char *approval=NULL,*binding=ffr3_unique_approval_binding(s->prepared,"ORIGINAL_OPERATION",&approval);if(!binding)return NULL;
    char *permission=ffr3_json_field(binding,"permission"),*inputs=permission?ffr3_format("[%s]",permission):NULL;
    char *admitted=inputs?ffr3_admission(s,"original.reserve","RESERVE_ORIGINAL",inputs,ffr3_now_ns()):NULL;
    int valid=admitted&&ffr3_dispatch(s,"NOT_DISPATCHED",NULL,"[]",0,0,1);
    unsigned long long started=ffr3_now_ns();if(valid)valid=ffr3_dispatch(s,"DISPATCHED",NULL,"[]",started,0,1)!=NULL;
    char kind_name[32];valid=valid&&ffr3_json_string_value(binding,"operation_kind",kind_name,sizeof(kind_name));
    char *native_reservation=valid&&!strcmp(kind_name,"FAILED_ACTIVE")?ffr3_failed_active_reservation(s,binding,permission):NULL;
    char *reservation=valid&&!strcmp(kind_name,"ORDINARY")?admitted:native_reservation;
    valid=valid&&reservation;
    char *predecessor=ffr3_json_field(s->prepared->lineage,"predecessor");
    char *source=ffr3_json_field(binding,"source"),*package=ffr3_json_field(binding,"package"),*kind=ffr3_json_field(binding,"operation_kind"),
      *generation=ffr3_json_field(binding,"generation"),*service=ffr3_json_field(binding,"service"),*from=ffr3_json_field(binding,"valid_from_ns"),*until=ffr3_json_field(binding,"valid_until_ns"),*prep=ffr3_json_field(s->prepared->pin,"preparation");
    /* The actual original controller has already retained the raw checkpoint.
     * P's existing admitted maintenance pulse publishes its once-only binding
     * only after comparing that checkpoint with its in-memory/live identity.
     * Observe the immutable receipt under this same original absolute budget;
     * no new request, retry of an operation or future proof is synthesized. */
    char *control=NULL;
    while(predecessor&&ffr3_budget(&s->prepared->stop)){
        int complete=0;control=ffr3_scan_proof(s,"CONTROL_BINDING",NULL,predecessor,&complete);
        if(control||!complete)break; /* Partial/ambiguous scan is a sticky denial. */
        struct timespec pause={0,10000000};nanosleep(&pause,NULL);
    }
    char *control_payload=control?ffr3_json_field(control,"payload"):NULL;
    char *control_ref=control_payload?ffr3_json_field(control_payload,"live_control"):NULL;
    char *authority_payload=valid&&approval&&source&&package&&kind&&generation&&service&&from&&until&&prep&&control_ref?
      ffr3_format("{\"approval\":%s,\"clock\":%s,\"control\":%s,\"generation\":%s,\"identity\":\"native-original-authority\",\"kind\":%s,\"package\":%s,\"preparation\":%s,\"process\":%s,\"reservation\":%s,\"service\":%s,\"source\":%s,\"valid_from_ns\":%s,\"valid_until_ns\":%s}",approval,s->prepared->clock,control_ref,generation,kind,package,prep,predecessor,reservation,service,source,from,until):NULL;
    char *authority=authority_payload?ffr3_signed_publish(s->prepared,&s->codec,"ORIGINAL_AUTHORITY",1,authority_payload,ffr3_now_ns()):NULL;
    char *native=predecessor?ffr3_native_process_proof(s,predecessor,"PROCESS_BIRTH"):NULL;
    char *process_evidence=native?ffr3_evidence(native):NULL,*cap_evidence=ffr3_evidence(s->capability),*control_evidence=control?ffr3_evidence(control):NULL;
    /* CONTROL_BINDING is P-owned; its evidence authority follows actual role. */
    if(control_evidence){char *role=ffr3_json_field(control,"role");if(role&&!strcmp(role,"\"PREDECESSOR\"")){char *a=strstr(control_evidence,"\"LAUNCHER\"");if(a){size_t before=(size_t)(a-control_evidence);char *fixed=ffr3_format("%.*s\"PREDECESSOR\"%s",(int)before,control_evidence,a+10);free(control_evidence);control_evidence=fixed;}}free(role);}
    char *custody_payload=authority&&process_evidence&&cap_evidence&&control_evidence?ffr3_format("{\"checkpoint_bytes\":\"%zu\",\"checkpoint_hash\":\"%s\",\"controller\":%s,\"controller_capability\":%s,\"execution_owner\":\"native-controller\",\"lineage\":%s,\"live_control\":%s,\"process_binding\":%s,\"verified_ns\":\"%llu\"}",s->control_bytes,s->codec.key_id,s->prepared->controller,cap_evidence,s->prepared->lineage,control_evidence,process_evidence,ffr3_now_ns()):NULL;
    char *custody=custody_payload?ffr3_signed_publish(s->prepared,&s->codec,"CUSTODY",0,custody_payload,ffr3_now_ns()):NULL;
    valid=custody&&ffr3_dispatch(s,"COMPLETED",NULL,"[]",started,ffr3_now_ns(),1);s->original_reserved=valid;
    free(approval);free(binding);free(permission);free(inputs);free(native_reservation);free(predecessor);free(source);free(package);free(kind);free(generation);free(service);free(from);free(until);free(prep);free(control);free(control_payload);free(control_ref);free(authority_payload);free(native);free(process_evidence);free(cap_evidence);free(control_evidence);free(custody_payload);free(custody);
    if(!valid){free(authority);return NULL;}return authority;
}

static int ffr3_capture_command(const char *executable,char *const arguments[],int expected,const struct timespec *stop) {
    int out[2];if(!failed_fenced_pipe(out))return 0;pid_t child=fork();if(child<0){close(out[0]);close(out[1]);return 0;}
    if(!child){int null=open("/dev/null",O_RDONLY);if(null<0||dup2(null,0)!=0||dup2(out[1],1)!=1||dup2(out[1],2)!=2)_exit(90);
        int maximum=getdtablesize();for(int fd=3;fd<maximum;fd++)if(close(fd)!=0&&errno!=EBADF)_exit(91);execv(executable,arguments);_exit(92);}
    close(out[1]);int valid=recovery_wait_io(out[0],POLLIN,stop);char extra;if(valid)valid=read(out[0],&extra,1)==0;close(out[0]);
    int status=0;pid_t joined;do{joined=waitpid(child,&status,0);}while(joined<0&&errno==EINTR);
    return valid&&joined==child&&WIFEXITED(status)&&WEXITSTATUS(status)==expected&&ffr3_budget(stop);
}
static char *ffr3_native_other_probe(FFR3Session *s,const char *subject,const char *kind) {
    char *native=NULL,*endpoint=NULL;char boot[128];unsigned long long now=0;
    if(!ffr3_json_string_value(s->prepared->clock,"boot_id",boot,sizeof(boot)))return NULL;
    if(!strcmp(kind,"LISTENER_ABSENT")){
        int slots=ffr3_child_directory(s->prepared->root,"slots"),slotfd=slots>=0?ffr3_child_directory(slots,s->slot):-1;size_t length=0;
        char *claim=slotfd>=0?ffr3_capture_at(slotfd,"claim",FFR3_MAX_RECORD,&length,1,&s->prepared->stop):NULL;
        char *body=claim?ffr3_json_field(claim,"payload"):NULL;endpoint=body?ffr3_json_field(body,"endpoint"):NULL;
        char port[16],argument[32];int valid=claim&&ffr3_native_verify(&s->codec,claim,0)&&endpoint&&ffr3_json_string_value(endpoint,"port",port,sizeof(port));
        if(valid){unsigned long value=strtoul(port,NULL,10);valid=value>=1&&value<=65535;}
        if(valid){snprintf(argument,sizeof(argument),"-iTCP:%s",port);char *arguments[]={"/usr/sbin/lsof","-nP","-Fpfn",argument,"-sTCP:LISTEN",NULL};valid=ffr3_capture_command(arguments[0],arguments,1,&s->prepared->stop);}
        if(slotfd>=0)close(slotfd);if(slots>=0)close(slots);free(claim);free(body);
        if(valid){now=ffr3_now_ns();native=ffr3_format("{\"adapter\":\"DARWIN_KERNEL_V1\",\"arguments\":[\"-nP\",\"-Fpfn\",\"-iTCP:%s\",\"-sTCP:LISTEN\"],\"boot_id\":\"%s\",\"endpoint\":%s,\"executable\":\"/usr/sbin/lsof\",\"exit\":\"1\",\"kind\":\"LISTENER_ABSENT\",\"observed_ns\":\"%llu\",\"observer\":%s,\"schema\":\"KRONOS_DARWIN_KERNEL_OBSERVATION_V1\",\"stderr\":\"\",\"stdout\":\"\",\"subject\":%s}",port,boot,endpoint,now,s->prepared->controller,subject);}
    }else if(!strcmp(kind,"CANONICAL_PARENT")&&!strcmp(subject,s->prepared->controller)){
        char *arguments[]={"/usr/bin/codesign","--verify","--deep","--strict","-R","=identifier \"com.project-kronos.browser-v1\"","/Applications/KRONOS.app",NULL};
        char actual[1024],digest[65];size_t bytes=0;
        if(ffr3_capture_command(arguments[0],arguments,0,&s->prepared->stop)&&ffr3_actual_native_process(actual,digest,&bytes)&&!strcmp(actual,subject)){
            char pid[32];if(ffr3_json_string_value(subject,"pid",pid,sizeof(pid))){now=ffr3_now_ns();native=ffr3_format("{\"adapter\":\"DARWIN_KERNEL_V1\",\"boot_id\":\"%s\",\"kernel_parent_pid\":\"%s\",\"kind\":\"CANONICAL_PARENT\",\"observed_ns\":\"%llu\",\"observer\":%s,\"resolved_image\":\"/Applications/KRONOS.app/Contents/MacOS/KRONOS\",\"schema\":\"KRONOS_DARWIN_KERNEL_OBSERVATION_V1\",\"signature_exit\":\"0\",\"signature_stderr\":\"\",\"subject\":%s}",boot,pid,now,s->prepared->controller,subject);}
        }
    }
    free(endpoint);if(!native)return NULL;char identity[256],hash[65],name[80];snprintf(identity,sizeof(identity),"native-%s-%llu",kind,now);
    char *ref=ffr3_blob_ref(identity,native);int valid=ref&&ffr3_json_string_value(ref,"hash",hash,sizeof(hash));
    if(valid){snprintf(name,sizeof(name),"%s.blob",hash);valid=ffr3_publish_immutable(s->prepared->blobs,name,native,strlen(native),&s->prepared->stop);}free(native);
    char *payload=valid?ffr3_format("{\"adapter\":\"DARWIN_KERNEL_V1\",\"boot_id\":\"%s\",\"identity\":\"%s-proof\",\"kind\":\"%s\",\"observed_ns\":\"%llu\",\"observer\":%s,\"raw\":%s,\"result\":\"%s\",\"subject\":%s}",boot,identity,kind,now,s->prepared->controller,ref,!strcmp(kind,"LISTENER_ABSENT")?"ABSENT":"MATCH",subject):NULL;free(ref);
    char *raw=payload?ffr3_signed_publish(s->prepared,&s->codec,"PLATFORM_OBSERVATION",1,payload,now):NULL;free(payload);return raw;
}
static char *ffr3_native_exchange(FFR3Session *s) {
    if(!s->claim_reserved||s->shutdown_sent||!ffr3_budget(&s->prepared->stop))return NULL;s->shutdown_sent=1;
    int slots=ffr3_child_directory(s->prepared->root,"slots"),slotfd=slots>=0?ffr3_child_directory(slots,s->slot):-1;size_t length=0;
    char *claim=slotfd>=0?ffr3_capture_at(slotfd,"claim",FFR3_MAX_RECORD,&length,1,&s->prepared->stop):NULL;
    if(slotfd>=0)close(slotfd);if(slots>=0)close(slots);
    char *payload=claim?ffr3_json_field(claim,"payload"):NULL,*endpoint=payload?ffr3_json_field(payload,"endpoint"):NULL;char port[16];
    int valid=claim&&ffr3_native_verify(&s->codec,claim,0)&&endpoint&&ffr3_json_string_value(endpoint,"port",port,sizeof(port));unsigned long number=valid?strtoul(port,NULL,10):0;
    if(!valid||number<1||number>65535){free(claim);free(payload);free(endpoint);return NULL;}
    /* Native C retains the canonical service lock. P independently reads the
     * immutable pin/claim without reacquiring this cross-process lock. */
    int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0){free(claim);free(payload);free(endpoint);return NULL;}
    fcntl(fd,F_SETFD,FD_CLOEXEC);fcntl(fd,F_SETFL,O_NONBLOCK);struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_port=htons((uint16_t)number);inet_pton(AF_INET,"127.0.0.1",&address.sin_addr);
    int connected=connect(fd,(struct sockaddr*)&address,sizeof(address));valid=connected==0||errno==EINPROGRESS;
    if(valid&&connected!=0){valid=recovery_wait_io(fd,POLLOUT,&s->prepared->stop);int error=0;socklen_t bytes=sizeof(error);if(valid)valid=getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&bytes)==0&&!error;}
    long process=0;char token[65]={0};if(sscanf(s->control,"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%64[0-9a-f]",&process,token)!=2)valid=0;
    char *request=valid?ffr3_format("POST /control/failed-fenced-recovery/v1 HTTP/1.0\r\nHost: 127.0.0.1:%s\r\nX-Kronos-Backend-Pid: %ld\r\nX-Kronos-Restart-Token: %s\r\nContent-Type: application/json\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s",port,process,token,length,claim):NULL;memset(token,0,sizeof(token));free(claim);free(payload);free(endpoint);
    if(valid)valid=request&&ffr3_helper_write(fd,request,strlen(request),&s->prepared->stop);if(request){memset(request,0,strlen(request));free(request);}
    char *response=malloc(131072+512);size_t used=0;int eof=0;
    while(valid&&used<131072+511){if(!recovery_wait_io(fd,POLLIN,&s->prepared->stop)){valid=0;break;}ssize_t n=read(fd,response+used,131072+511-used);if(n<0&&(errno==EINTR||errno==EAGAIN))continue;if(n<0){valid=0;break;}if(!n){eof=1;break;}used+=(size_t)n;}
    close(fd);if(!response)return NULL;response[used]=0;valid=valid&&eof&&!memchr(response,0,used);
    char *body=valid?strstr(response,"\r\n\r\n"):NULL;char *expected=NULL;
    if(body){body+=4;size_t bytes=used-(size_t)(body-response);expected=ffr3_format("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n",bytes);
        valid=bytes>=1&&bytes<=131072&&expected&&strlen(expected)==(size_t)(body-response)&&!memcmp(response,expected,strlen(expected))&&ffr3_native_verify(&s->codec,body,0);}
    else valid=0;free(expected);char *result=NULL;
    if(valid){s->ack=strdup(body);s->ack_received_ns=ffr3_now_ns();char *hex=ffr3_bytes_hex(body,strlen(body));result=hex?ffr3_format("{\"ack\":\"%s\",\"received_ns\":\"%llu\"}",hex,s->ack_received_ns):NULL;free(hex);}
    free(response);return result;
}
static const char *ffr3_child_pin_template = "import os,sys,time,json,hashlib,types,stat,importlib.abc,importlib.util\norigin,stop=__KRONOS_ORIGIN__,__KRONOS_STOP__\nframe_hex=__KRONOS_FRAME_HEX__\ndef check():\n    current=globals().get('capsule')\n    if current is not None and getattr(current,'ready_session',None) is not None:\n        from tools.runtime_source_gate import native_child_ready_budget\n        native_child_ready_budget(current).check();return\n    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)\n    if stop!=origin+15000000000 or not origin<=now<stop:raise RuntimeError('NATIVE_CHILD_PIN_BUDGET')\ndef pairs(rows):\n    result={}\n    for key,value in rows:\n        if key in result:raise RuntimeError('NATIVE_CHILD_PIN_DUPLICATE')\n        result[key]=value\n    return result\ncheck()\nraw=bytes.fromhex(frame_hex)\nif not 1<=len(raw)<=67108864:raise RuntimeError('NATIVE_CHILD_PIN_BOUND')\nframe=json.loads(raw,object_pairs_hook=pairs)\nif json.dumps(frame,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()!=raw or set(frame)!={'inventory','plan','plan_hash','sources'}:raise RuntimeError('NATIVE_CHILD_PIN_CANONICAL')\nplan=frame['plan'];planraw=json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()\nif hashlib.sha256(planraw).hexdigest()!=frame['plan_hash'] or set(plan)!={'schema','identity','source_inventory','modules','qualification'} or plan['schema']!='KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0':raise RuntimeError('NATIVE_CHILD_PIN_PLAN')\ninventory=frame['inventory'];inventory_raw=json.dumps(inventory,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()\nif type(inventory) is not list or not 1<=len(inventory)<=4096 or any(type(row) is not list or len(row)!=2 or any(type(value) is not str for value in row) for row in inventory):raise RuntimeError('NATIVE_CHILD_PIN_INVENTORY')\nif hashlib.sha256(inventory_raw).hexdigest()!=plan['source_inventory']['hash'] or str(len(inventory_raw))!=plan['source_inventory']['bytes']:raise RuntimeError('NATIVE_CHILD_PIN_INVENTORY_HASH')\nexpected=dict(inventory)\nif len(expected)!=len(inventory) or list(expected)!=sorted(expected):raise RuntimeError('NATIVE_CHILD_PIN_MODULES')\nplanned={row['name']:row['digest'] for row in plan['modules']}\nif len(planned)!=len(plan['modules']) or list(planned)!=sorted(planned) or any(expected.get(name)!=digest for name,digest in planned.items()):raise RuntimeError('NATIVE_CHILD_PIN_PLAN_SOURCE')\ndef capture(path):\n    if type(path) is not str or not path.startswith('/') or '\\x00' in path:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PATH')\n    parts=path.split('/')[1:]\n    if not parts or any(part in {'','.','..'} for part in parts):raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PATH')\n    flags=os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW\n    parent=os.open('/',flags|os.O_DIRECTORY);ancestors=[]\n    try:\n        for part in parts[:-1]:\n            child=os.open(part,flags|os.O_DIRECTORY,dir_fd=parent)\n            os.close(parent);parent=child\n            st=os.fstat(parent);ancestors.append((st.st_dev,st.st_ino,st.st_uid,st.st_mode))\n            if st.st_uid not in {0,os.getuid()} or st.st_mode&0o022:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PARENT')\n        descriptor=os.open(parts[-1],flags,dir_fd=parent)\n        try:\n            before=os.fstat(descriptor)\n            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid not in {0,os.getuid()} or before.st_mode&0o022 or not 0<=before.st_size<=16777216:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PRIVATE')\n            chunks=[];total=0\n            while True:\n                check();part=os.read(descriptor,65536)\n                if not part:break\n                total+=len(part)\n                if total>16777216:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_BOUND')\n                chunks.append(part)\n            after=os.fstat(descriptor);named=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)\n            fields=('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')\n            if any(getattr(before,k)!=getattr(after,k) or getattr(before,k)!=getattr(named,k) for k in fields):raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_CHANGED')\n            reopened=os.open('/',flags|os.O_DIRECTORY)\n            try:\n                for index,part in enumerate(parts[:-1]):\n                    child=os.open(part,flags|os.O_DIRECTORY,dir_fd=reopened)\n                    os.close(reopened);reopened=child;st=os.fstat(reopened)\n                    if (st.st_dev,st.st_ino,st.st_uid,st.st_mode)!=ancestors[index]:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PARENT_CHANGED')\n            finally:os.close(reopened)\n            return b''.join(chunks)\n        finally:os.close(descriptor)\n    finally:os.close(parent)\nsources={}\nfor row in frame['sources']:\n    check()\n    if set(row)!={'name','package','path'} or type(row['package']) is not bool or row['name'] in sources:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE')\n    try:payload=capture(row['path'])\n    except OSError:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_UNAVAILABLE') from None\n    if expected.get(row['name'])!=hashlib.sha256(payload).hexdigest():raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_HASH')\n    sources[row['name']]=(payload,row['package'],row['path'])\nif set(sources)!=set(expected) or not {'tools.kronos_browser','kronos.intraday.runtime_identity','tools.runtime_source_gate'}<=set(sources):raise RuntimeError('NATIVE_CHILD_PIN_ROSTER')\ncapsule=types.ModuleType('_kronos_native_child_bootstrap')\ncapsule.pid=os.getpid();capsule.origin=origin;capsule.stop=stop;capsule.frame_hex=frame_hex\ncapsule.script=sys.orig_argv[sys.orig_argv.index('-c')+1];capsule.plan_hash=frame['plan_hash']\ncapsule.sources=tuple((name,sources[name]) for name in sorted(sources));capsule.plan=planraw\nconstructed={}\nclass PinnedLoader(importlib.abc.Loader):\n    def __init__(self,name):\n        if name not in sources or name in constructed:raise RuntimeError('NATIVE_CHILD_PIN_REPLAY')\n        self.name=name;self.payload=sources[name][0];self.path=sources[name][2]\n        self.code=compile(self.payload,self.path,'exec',dont_inherit=True);self.executed=False\n        constructed[name]=self\n    def create_module(self,spec):return None\n    def exec_module(self,module):\n        check()\n        if module.__spec__.loader is not self or module.__spec__.name!=self.name or self.executed:raise RuntimeError('NATIVE_CHILD_PIN_LOADER_CHANGED')\n        self.executed=True;module.__file__=self.path;exec(self.code,module.__dict__)\n    def is_package(self,name):return sources[name][1]\nclass PinnedFinder(importlib.abc.MetaPathFinder):\n    def find_spec(self,name,path=None,target=None):\n        if name in sources:return importlib.util.spec_from_loader(name,PinnedLoader(name),is_package=sources[name][1])\n        if name in {'tools','tools.macos'} and name not in sources and any(key.startswith(name+'.') for key in sources):\n            spec=importlib.util.spec_from_loader(name,loader=None,is_package=True);spec.submodule_search_locations=[];return spec\n        if name in {'tools','kronos'} or name.startswith(('tools.','kronos.')):raise ImportError('NATIVE_CHILD_PIN_UNCAPTURED_MODULE')\ncapsule.loader_type=PinnedLoader;capsule.constructed=constructed;capsule.finder=PinnedFinder()\nsys.modules[capsule.__name__]=capsule;sys.meta_path.insert(0,capsule.finder)\ncheck()\nfrom tools import kronos_browser as entry\nraise SystemExit(entry.main(['--no-browser']))\n";

static char *ffr3_replace_once(const char *text,const char *marker,const char *value) {
    const char *where=strstr(text,marker);if(!where||strstr(where+strlen(marker),marker))return NULL;
    return ffr3_format("%.*s%s%s",(int)(where-text),text,value,where+strlen(marker));
}
static char *ffr3_evidence_blob(const char *evidence) {
    char identity[256],hash[65],bytes[32];
    if(!ffr3_json_string_value(evidence,"identity",identity,sizeof(identity))||!ffr3_json_string_value(evidence,"hash",hash,sizeof(hash))||!ffr3_json_string_value(evidence,"bytes",bytes,sizeof(bytes)))return NULL;
    return ffr3_format("{\"bytes\":\"%s\",\"hash\":\"%s\",\"identity\":\"%s\"}",bytes,hash,identity);
}
static char *ffr3_source_map(FFR3PreparedNative *p,const char *repository,const char *plan,const char *plan_ref) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return NULL;char hash[65];
    char *inventory=NULL,*capture=ffr3_capture_inventory(p,plan,&inventory);
    if(!capture||!ffr3_canonical_object(j,capture)||!ffr3_json_string_value(plan_ref,"hash",hash,sizeof(hash))){free(capture);free(inventory);free(j);return NULL;}
    int modules=recovery_json_get(j,0,"modules");if(modules<0||j->token[modules].kind!='['||j->token[modules].count>4096){free(capture);free(inventory);free(j);return NULL;}
    FFR3Buffer output={0};int valid=ffr3_text(&output,"{\"inventory\":")&&ffr3_text(&output,inventory)&&ffr3_text(&output,",\"plan\":")&&ffr3_text(&output,plan)&&ffr3_text(&output,",\"plan_hash\":")&&ffr3_quote(&output,hash)&&ffr3_text(&output,",\"sources\":[");
    unsigned count=0;char before[128]={0};
    for(int item=modules+1;valid&&item<j->token[modules].next;item=j->token[item].next){
        char name[128],expected[65],path[PATH_MAX];int package=0;valid=j->token[item].count==2&&recovery_string(j,item,"name",name,sizeof(name))&&recovery_string(j,item,"digest",expected,sizeof(expected))&&valid_token(expected)&&(!*before||strcmp(before,name)<0)&&ffr3_module_path(repository,name,path,&package)&&ffr3_budget(&p->stop);
        if(!valid)break;strcpy(before,name);
        /* C verifies the approved names/paths now; child captures each exact
         * file before any imports and proves its executed byte object later. */
        valid=ffr3_text(&output,count++?",{\"name\":":"{\"name\":")&&ffr3_quote(&output,name)&&ffr3_text(&output,package?",\"package\":true,\"path\":":",\"package\":false,\"path\":")&&ffr3_quote(&output,path)&&ffr3_text(&output,"}");
    }
    free(j);free(capture);free(inventory);valid=valid&&count&&ffr3_text(&output,"]}");if(!valid){free(output.bytes);return NULL;}return output.bytes;
}
static char *ffr3_product_script(FFR3Session *s,const char *repository) {
    char *intent=ffr3_json_field(s->intent,"payload"),*target=intent?ffr3_json_field(intent,"successor_source"):NULL,*target_ref=target?ffr3_evidence_blob(target):NULL;
    char *target_raw=target_ref?ffr3_blob_at(s->prepared->blobs,target_ref,"blob",&s->prepared->stop):NULL,*payload=target_raw?ffr3_json_field(target_raw,"payload"):NULL;
    char *plan_ref=payload?ffr3_json_field(payload,"bootstrap_plan"):NULL,*plan=plan_ref?ffr3_blob_at(s->prepared->blobs,plan_ref,"blob",&s->prepared->stop):NULL;
    char *map=plan&&target_raw&&ffr3_native_verify(&s->codec,target_raw,1)?ffr3_source_map(s->prepared,repository,plan,plan_ref):NULL;
    char *hex=map?ffr3_bytes_hex(map,strlen(map)):NULL,*quoted=hex?ffr3_format("'%s'",hex):NULL;
    unsigned long long origin=(unsigned long long)s->prepared->origin.tv_sec*1000000000ULL+(unsigned long long)s->prepared->origin.tv_nsec;char start[32],stop[32];snprintf(start,sizeof(start),"%llu",origin);snprintf(stop,sizeof(stop),"%llu",origin+15000000000ULL);
    char *a=quoted?ffr3_replace_once(ffr3_child_pin_template,"__KRONOS_FRAME_HEX__",quoted):NULL,*b=a?ffr3_replace_once(a,"__KRONOS_ORIGIN__",start):NULL,*script=b?ffr3_replace_once(b,"__KRONOS_STOP__",stop):NULL;
    free(intent);free(target);free(target_ref);free(target_raw);free(payload);free(plan_ref);free(plan);free(map);free(hex);free(quoted);free(a);free(b);return script;
}

/* Static installation metadata is selected by the actual native image and
 * canonical guard installation. It is not an operational permission. */
static int ffr3_static_catalogue_match(const FFR3PreparedNative *p,const char *catalogue,char **backend_plan,char **backend_plan_ref) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return 0;int valid=ffr3_canonical_object(j,catalogue),rows=valid?recovery_json_get(j,0,"rows"):-1;char *source=NULL;unsigned guards=0,artifacts=0;
    if(rows<0){free(j);return 0;}
    for(int item=rows+1;item<j->token[rows].next;item=j->token[item].next){
        if(!recovery_field(j,item,"purpose","GUARD")||!recovery_field(j,item,"authority","CA"))continue;
        int binding=recovery_json_get(j,item,"bindings"),launcher=recovery_json_get(j,binding,"launcher");char hash[65];
        if(recovery_field(j,binding,"classification","MANDATORY")&&recovery_string(j,launcher,"hash",hash,sizeof(hash))&&!strcmp(hash,p->executable_hash)){
            guards++;free(source);source=ffr3_json_value(j,recovery_json_get(j,binding,"source_inventory"));}
    }
    if(guards!=1||!source){free(source);free(j);return 0;}
    for(int item=rows+1;item<j->token[rows].next;item=j->token[item].next){
        if(!recovery_field(j,item,"purpose","ARTIFACT")||!recovery_field(j,item,"authority","CA"))continue;
        int binding=recovery_json_get(j,item,"bindings");char *candidate=ffr3_json_value(j,recovery_json_get(j,binding,"source_inventory"));
        char *candidate_package=ffr3_json_value(j,recovery_json_get(j,binding,"package")),*installed_package=p->record?ffr3_json_field(p->record,"launcher_package"):NULL;
        if(candidate&&candidate_package&&installed_package&&!strcmp(candidate,source)&&!strcmp(candidate_package,installed_package)){
            char *ref=ffr3_json_value(j,recovery_json_get(j,binding,"bootstrap_plan"));
            char *plan=ref?ffr3_blob_at(p->blobs,ref,"blob",&p->stop):NULL;
            if(plan){artifacts++;if(artifacts==1){*backend_plan=plan;*backend_plan_ref=ref;plan=ref=NULL;}}
            free(plan);free(ref);
        }free(candidate);free(candidate_package);free(installed_package);
    }
    free(source);free(j);return artifacts==1;
}
static int ffr3_select_static_context(FFR3PreparedNative *p,char **plan,char **plan_ref) {
    DIR *directory=ffr3_directory_stream(p->preparation);if(!directory)return 0;struct dirent *entry;unsigned visited=0;int found=0,valid=1;
    while(valid&&(entry=readdir(directory))){const char *name=entry->d_name;if(!strcmp(name,".")||!strcmp(name,"..")||!strcmp(name,"records"))continue;
        if(++visited>8192){valid=0;break;}if(strlen(name)==73&&!strcmp(name+64,".approval"))continue;
        if(strlen(name)!=68||strcmp(name+64,".pin")){valid=0;break;}
        size_t bytes=0;char *pin=ffr3_capture_at(p->preparation,name,FFR3_MAX_RECORD,&bytes,1,&p->stop),*preparation=pin?ffr3_json_field(pin,"preparation"):NULL,*catalogue_ref=pin?ffr3_json_field(pin,"catalogue"):NULL;
        char *record=preparation?ffr3_blob_at(p->preparation_records,preparation,"json",&p->stop):NULL,*catalogue=catalogue_ref?ffr3_blob_at(p->preparation_records,catalogue_ref,"json",&p->stop):NULL;
        char approval_name[96];snprintf(approval_name,sizeof(approval_name),"%.*s.approval",64,name);char *approval=ffr3_capture_at(p->preparation,approval_name,FFR3_MAX_RECORD,&bytes,1,&p->stop);
        char *clock=record?ffr3_json_field(record,"clock"):NULL,*candidate_plan=NULL,*candidate_ref=NULL;
        if(!pin||!record||!catalogue||!approval||!clock){valid=0;}
        else if(ffr3_kernel_boot(clock)&&ffr3_json_string_value(record,"mode",(char[32]){0},32)&&strstr(record,"\"mode\":\"ORIGINAL\"")){
            FFR3PreparedNative view=*p;view.record=record;
            int matches=ffr3_static_catalogue_match(&view,catalogue,&candidate_plan,&candidate_ref);
            if(matches){
            if(found&&strcmp(*plan_ref,candidate_ref)){valid=0;}
            if(!found){found=1;p->pin=pin;pin=NULL;p->record=record;record=NULL;p->catalogue=catalogue;catalogue=NULL;p->approval=approval;approval=NULL;p->clock=clock;clock=NULL;*plan=candidate_plan;candidate_plan=NULL;*plan_ref=candidate_ref;candidate_ref=NULL;}
            }
        }
        free(pin);free(preparation);free(catalogue_ref);free(record);free(catalogue);free(approval);free(clock);free(candidate_plan);free(candidate_ref);
    }
    closedir(directory);return valid&&found;
}
static int ffr3_open_static(FFR3PreparedNative *p,char **plan,char **plan_ref) {
    memset(p,0,sizeof(*p));p->root=p->preparation=p->preparation_records=p->blobs=p->records=p->lock=-1;
    if(clock_gettime(CLOCK_MONOTONIC,&p->origin)!=0||!ffr3_actual_native_process(p->controller,p->executable_hash,&p->executable_size))return 0;p->stop=p->origin;p->stop.tv_sec+=15;
    char estate[PATH_MAX];if(!ffr3_fixed_estate(estate))return 0;
    p->root=open(estate,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(p->root<0||!ffr3_private_directory(p->root))goto failed;
    p->preparation=ffr3_child_directory(p->root,"preparation");p->preparation_records=p->preparation>=0?ffr3_child_directory(p->preparation,"records"):-1;p->blobs=ffr3_child_directory(p->root,"blobs");p->records=ffr3_child_directory(p->root,"records");
    if(p->preparation<0||p->preparation_records<0||p->blobs<0||p->records<0||!ffr3_select_static_context(p,plan,plan_ref))goto failed;
    p->mode=ffr3_json_field(p->record,"mode");p->lineage=ffr3_json_field(p->record,"lineage");p->attempt=ffr3_json_field(p->record,"attempt");
    if(!p->mode||!p->lineage||!p->attempt)goto failed;
    return 1;
 failed:ffr3_release_preparation(p);return 0;
}
static char *ffr3_script_for_map(const char *map,const struct timespec *origin) {
    char *hex=ffr3_bytes_hex(map,strlen(map)),*quoted=hex?ffr3_format("'%s'",hex):NULL;free(hex);if(!quoted)return NULL;
    unsigned long long now=(unsigned long long)origin->tv_sec*1000000000ULL+(unsigned long long)origin->tv_nsec;char a[32],b[32];snprintf(a,sizeof(a),"%llu",now);snprintf(b,sizeof(b),"%llu",now+15000000000ULL);
    char *first=ffr3_replace_once(ffr3_child_pin_template,"__KRONOS_FRAME_HEX__",quoted),*second=first?ffr3_replace_once(first,"__KRONOS_ORIGIN__",a):NULL,*result=second?ffr3_replace_once(second,"__KRONOS_STOP__",b):NULL;
    free(quoted);free(first);free(second);return result;
}
/* A closed original helper's retained factual outputs can be re-attested by
 * this actual staged C before its separately approved recovery operation.
 * No package/signature/currentness check occurs here; operational use repeats
 * those real predicates under its own existing shared 15-second clock. */
static int ffr3_fact_catalogue_match(FFR3PreparedNative *p,const char *kind,const char *payload) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j||!ffr3_canonical_object(j,p->catalogue)){free(j);return 0;}
    char id[256];const char *approval=!strcmp(kind,"PACKAGE")?"artifact_approval":"approval";
    if(!ffr3_json_string_value(payload,approval,id,sizeof(id))){free(j);return 0;}
    int rows=recovery_json_get(j,0,"rows"),found=0;if(rows<0){free(j);return 0;}
    for(int row=rows+1;row<j->token[rows].next;row=j->token[row].next){
        if(!recovery_field(j,row,"identity",id)||!recovery_field(j,row,"authority","CA")||!recovery_field(j,row,"purpose","ARTIFACT"))continue;
        int b=recovery_json_get(j,row,"bindings");int valid=1;
        const char *target_fields[]={"bootstrap_plan","capability_manifest","configuration","package","revision","source_inventory"};
        const char *package_fields[]={"manifest","executable"};const char **fields=!strcmp(kind,"PACKAGE")?package_fields:target_fields;size_t count=!strcmp(kind,"PACKAGE")?2:6;
        for(size_t n=0;valid&&n<count;n++){
            const char *native_key=!strcmp(fields[n],"manifest")?"package":fields[n];char *left=ffr3_json_field(payload,fields[n]),*right=ffr3_json_value(j,recovery_json_get(j,b,native_key));
            valid=left&&right&&!strcmp(left,right);free(left);free(right);
        }if(valid)found++;
    }free(j);return found==1;
}
static char *ffr3_replace_field(const char *raw,const char *key,const char *value) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return NULL;int valid=ffr3_canonical_object(j,raw),field=valid?recovery_json_get(j,0,key):-1;
    char *out=field>=0?ffr3_format("%.*s%s%s",(int)ffr3_token_start(j,field),raw,value,raw+ffr3_token_end(j,field)):NULL;free(j);return out;
}
static int ffr3_stage_retained_facts(void) {
    FFR3PreparedNative p;char *plan=NULL,*plan_ref=NULL;
    if(!ffr3_open_static(&p,&plan,&plan_ref))return 0;free(plan);free(plan_ref);
    int parent=openat(p.root,"..",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);size_t control_bytes=0;
    char *control=parent>=0?ffr3_capture_at(parent,"browser-backend-v1.control",255,&control_bytes,1,&p.stop):NULL;if(parent>=0)close(parent);
    FFR3NativeCodec codec;memset(&codec,0,sizeof(codec));int valid=control&&ffr3_native_codec_init(&codec,control,p.clock,p.controller);
    if(control){memset(control,0,control_bytes);free(control);}char *facts[4]={0};unsigned matches=0;size_t visited=0,total=0;
    DIR *directory=valid?ffr3_directory_stream(p.blobs):NULL;struct dirent *entry;if(!directory)valid=0;
    while(valid&&(entry=readdir(directory))){const char *name=entry->d_name;if(!strcmp(name,".")||!strcmp(name,".."))continue;
        if(++visited>4096||strlen(name)!=69||strcmp(name+64,".blob")){valid=0;break;}
        size_t length=0;char *raw=ffr3_capture_at(p.blobs,name,16U*FFR3_MAX_RECORD,&length,1,&p.stop);if(!raw||total+length>64U*1024U*1024U){free(raw);valid=0;break;}total+=length;
        char kind[96];if(length>FFR3_MAX_RECORD||memchr(raw,0,length)||!ffr3_json_string_value(raw,"kind",kind,sizeof(kind))||strcmp(kind,"CONTROLLER_DISPATCH")){free(raw);continue;}
        unsigned char digest[32];char hash[65];CC_SHA256(raw,(CC_LONG)length,digest);ffr3_hex(digest,hash);
        char *body=ffr3_json_field(raw,"payload");RecoveryJson *j=calloc(1,sizeof(*j));
        int candidate=!memcmp(name,hash,64)&&ffr3_native_verify(&codec,raw,1)&&body&&j&&ffr3_canonical_object(j,body)&&
            recovery_field(j,0,"state","COMPLETED")&&recovery_field(j,0,"outcome","JOINED_SUCCESS");
        int output=candidate?recovery_json_get(j,0,"outputs"):-1;char *selected[4]={0};unsigned n=0;
        if(output>=0&&j->token[output].kind=='['&&j->token[output].count==4){
            for(int item=output+1;item<j->token[output].next;item=j->token[item].next){
                char *ref=ffr3_json_value(j,item),*fact=ref?ffr3_blob_at(p.blobs,ref,"blob",&p.stop):NULL;free(ref);
                const char *fact_kind=fact&&(strstr(fact,"\"artifact_approval\":")!=NULL)?"PACKAGE":fact&&strstr(fact,"\"restoration_plan\":")?"TARGET_ARTIFACT":"COMPATIBILITY";
                int at=!strcmp(fact_kind,"TARGET_ARTIFACT")?0:!strcmp(fact_kind,"COMPATIBILITY")?3:-1;
                if(at<0){char role[32];if(fact&&ffr3_json_string_value(fact,"role",role,sizeof(role)))at=!strcmp(role,"INSTALLED")?1:!strcmp(role,"ROLLBACK")?2:-1;}
                if(!fact||at<0||selected[at]||!ffr3_fact_payload(fact_kind,fact)||
                    (at!=3&&!ffr3_fact_catalogue_match(&p,fact_kind,fact))){free(fact);n=0;break;}
                selected[at]=fact;n++;
            }
            if(n==4){
                char *predecessor=ffr3_json_field(selected[3],"predecessor"),*source=predecessor?ffr3_blob_at(p.blobs,predecessor,"blob",&p.stop):NULL,
                    *sp=source?ffr3_json_field(source,"payload"):NULL,*process=sp?ffr3_json_field(sp,"process"):NULL,
                    *target=ffr3_blob_ref("target-fact",selected[0]),*successor=ffr3_json_field(selected[3],"successor"),
                    *installed=ffr3_json_field(selected[1],"manifest"),*rollback=ffr3_json_field(selected[2],"manifest");
                char actual[32],pid[32],from[32],until[32];snprintf(actual,sizeof(actual),"%ld",(long)codec.predecessor);
                int eligible=source&&ffr3_native_verify(&codec,source,1)&&process&&ffr3_json_string_value(process,"pid",pid,sizeof(pid))&&!strcmp(pid,actual)&&
                    target&&successor&&installed&&rollback&&strcmp(installed,rollback)&&ffr3_json_string_value(body,"started_ns",from,sizeof(from))&&ffr3_json_string_value(body,"completed_ns",until,sizeof(until));
                char expected_hash[65],actual_hash[65];if(eligible)eligible=ffr3_json_string_value(target,"hash",expected_hash,sizeof(expected_hash))&&
                    ffr3_json_string_value(successor,"hash",actual_hash,sizeof(actual_hash))&&!strcmp(expected_hash,actual_hash);
                for(size_t i=1;eligible&&i<4;i++){char at[32];eligible=ffr3_json_string_value(selected[i],"verified_ns",at,sizeof(at))&&
                    strtoull(from,NULL,10)<=strtoull(at,NULL,10)&&strtoull(at,NULL,10)<=strtoull(until,NULL,10);}
                if(eligible){matches++;if(matches==1)for(size_t i=0;i<4;i++){facts[i]=selected[i];selected[i]=NULL;}}
                free(predecessor);free(source);free(sp);free(process);free(target);free(successor);free(installed);free(rollback);
            }
        }
        for(size_t i=0;i<4;i++)free(selected[i]);free(j);free(body);free(raw);if(matches>1){valid=0;break;}
    }
    if(directory)closedir(directory);
    /* ORIGINAL staging has no prior factual batch yet. Absence grants nothing
     * and is reported explicitly; a recovery pin requiring facts still denies. */
    if(valid&&matches==0){puts("{\"retained_facts\":null}");fflush(stdout);goto done;}
    valid=valid&&matches==1;char *wrappers[4]={0},*refs[4]={0};const char *kinds[]={"TARGET_ARTIFACT","PACKAGE","PACKAGE","COMPATIBILITY"};
    for(size_t i=0;valid&&i<4;i++){
        if(i==3){char *rebound=ffr3_replace_field(facts[3],"successor",refs[0]);free(facts[3]);facts[3]=rebound;if(!rebound){valid=0;break;}}
        wrappers[i]=ffr3_signed_publish(&p,&codec,kinds[i],1,facts[i],ffr3_now_ns());refs[i]=wrappers[i]?ffr3_proof_blob(wrappers[i]):NULL;valid=refs[i]!=NULL;
    }
    if(valid){printf("{\"retained_facts\":{\"compatibility\":%s,\"installed_package\":%s,\"rollback_package\":%s,\"target\":%s}}\n",refs[3],refs[1],refs[2],refs[0]);fflush(stdout);}
    for(size_t i=0;i<4;i++){free(wrappers[i]);free(refs[i]);}
 done:for(size_t i=0;i<4;i++)free(facts[i]);memset(&codec,0,sizeof(codec));ffr3_release_preparation(&p);return valid;
}

static int ffr3_run_broker(FFR3Session *s,const char *python,const char *pin_frame,size_t pin_bytes,const char *context);
static int ffr3_static_guard(FFR3PreparedNative *p,const char *repository,const char *python) {
    p->lock=openat(p->root,"service.lock",O_RDWR|O_NOFOLLOW|O_CLOEXEC);struct stat metadata;
    if(p->lock<0||fstat(p->lock,&metadata)!=0||!S_ISREG(metadata.st_mode)||metadata.st_uid!=geteuid()||metadata.st_nlink!=1||(metadata.st_mode&0777)!=0600){fputs("KRONOS_R3_STARTUP_GATE:GUARD_LOCK_UNAVAILABLE\n",stderr);return 0;}
    while(flock(p->lock,LOCK_EX|LOCK_NB)!=0){if(errno!=EWOULDBLOCK||!ffr3_budget(&p->stop))return 0;struct timespec pause={0,1000000};nanosleep(&pause,NULL);}
    if(!ffr3_select_launcher_artifact(p)){fputs("KRONOS_R3_STARTUP_GATE:GUARD_ARTIFACT_UNAVAILABLE\n",stderr);return 0;}
    FFR3Session session={0};session.prepared=p;session.grant_writer=-1;session.read_only=1;
    /* This reader owns no current control/key and performs no custody write.
     * Historical VERIFY acquires only each retained record's own exact key. */
    int valid=strlen(p->clock)<sizeof(session.codec.clock)&&strlen(p->controller)<sizeof(session.codec.controller);
    if(valid){strcpy(session.codec.clock,p->clock);strcpy(session.codec.controller,p->controller);}
    char entry[512]={0};size_t length=0;char *frame=valid?ffr3_build_pin_frame(p,repository,entry,&length):NULL,*context=frame?ffr3_session_context(&session,"GUARD_ADMISSION",entry):NULL;
    if(valid&&!frame)fputs("KRONOS_R3_STARTUP_GATE:GUARD_SOURCE_UNAVAILABLE\n",stderr);
    if(frame&&!context)fputs("KRONOS_R3_STARTUP_GATE:GUARD_CONTEXT_UNAVAILABLE\n",stderr);
    valid=frame&&context&&ffr3_run_broker(&session,python,frame,length,context);
    if(frame&&context&&!valid)fputs("KRONOS_R3_STARTUP_GATE:GUARD_READER_UNAVAILABLE\n",stderr);
    free(frame);free(context);free(session.helper_process);if(session.control){memset(session.control,0,session.control_bytes);free(session.control);}memset(&session.codec,0,sizeof(session.codec));return valid;
}
static int ffr3_run_broker(FFR3Session *s,const char *python,const char *pin_frame,size_t pin_bytes,const char *context);
static char *ffr3_ordinary_pin_script(const char *repository,const char *python,FFR3PreparedNative *p) {
    char *plan=NULL,*plan_ref=NULL;if(!ffr3_open_static(p,&plan,&plan_ref)){
        fputs("KRONOS_R3_STARTUP_GATE:STATIC_PREPARATION_UNAVAILABLE\n",stderr);return NULL;}
    int guarded=ffr3_static_guard(p,repository,python);
    if(!guarded)fputs("KRONOS_R3_STARTUP_GATE:GUARD_NOT_VERIFIED\n",stderr);
    char *map=guarded?ffr3_source_map(p,repository,plan,plan_ref):NULL,*script=map?ffr3_script_for_map(map,&p->origin):NULL;
    if(guarded&&!script)fputs("KRONOS_R3_STARTUP_GATE:PINNED_SOURCE_UNAVAILABLE\n",stderr);
    free(map);free(plan);free(plan_ref);if(!script)ffr3_release_preparation(p);return script;
}

static char *ffr3_native_fork(FFR3Session *s) {
    if(!s->intent_reserved||s->fork_spent||!s->ack||!ffr3_budget(&s->prepared->stop))return NULL;s->fork_spent=1;
    struct passwd *account=getpwuid(geteuid());char repository[PATH_MAX],python[PATH_MAX],entry[PATH_MAX],python_path[PATH_MAX*2];
    if(!account||!discover_repository(account->pw_dir,repository)||snprintf(python,sizeof(python),"%s/.venv/bin/python",repository)>=(int)sizeof(python)||snprintf(entry,sizeof(entry),"%s/tools/kronos_browser.py",repository)>=(int)sizeof(entry)||snprintf(python_path,sizeof(python_path),"%s/src:%s",repository,repository)>=(int)sizeof(python_path))return NULL;
    char *script=ffr3_product_script(s,repository);if(!script)return NULL;
    extern char **environ;size_t arguments=strlen(script)+strlen(python)+4096;for(char **row=environ;*row;row++)arguments+=strlen(*row)+1;
    long maximum_arguments=sysconf(_SC_ARG_MAX);if(maximum_arguments<1||arguments>(size_t)maximum_arguments){free(script);return NULL;}
    int channel[2];if(!failed_fenced_pipe(channel)){free(script);return NULL;}if(!ffr3_budget(&s->prepared->stop)){close(channel[0]);close(channel[1]);free(script);return NULL;}s->fork_enter_ns=ffr3_now_ns();s->ready_deadline=(struct timespec){(time_t)(s->fork_enter_ns/1000000000ULL+120),(long)(s->fork_enter_ns%1000000000ULL)};
    pid_t child=fork();s->product=child;if(child<0){close(channel[0]);close(channel[1]);free(script);return NULL;}
    if(!child){
        if(!failed_fenced_child_descriptor(channel[0],channel[1])||setsid()<0)_exit(91);int null=open("/dev/null",O_RDWR);if(null<0||dup2(null,0)!=0||dup2(null,1)!=1||dup2(null,2)!=2)_exit(92);if(null>3)close(null);
        if(chdir(repository)!=0||setenv("PYTHONPATH",python_path,1)!=0||setenv("KRONOS_FAILED_FENCED_RECOVERY_VERSION","1.0.0",1)!=0||setenv("KRONOS_FAILED_FENCED_RECOVERY_SLOT",s->slot,1)!=0||setenv("KRONOS_FAILED_FENCED_RECOVERY_CHILD_NONCE",s->nonce,1)!=0)_exit(93);
        const char *old[]={"KRONOS_MAINTENANCE_GENERATION","KRONOS_MAINTENANCE_PARENT","KRONOS_MAINTENANCE_PROOF","KRONOS_MAINTENANCE_PROTOCOL","KRONOS_MAINTENANCE_REVISION","KRONOS_LEGACY_BOOTSTRAP_ID","KRONOS_LEGACY_BOOTSTRAP_PROOF","KRONOS_LAUNCH_MODE","KRONOS_REPLACEMENT_REVISION","KRONOS_RECOVERY_ATTEMPT"};
        for(size_t i=0;i<sizeof(old)/sizeof(old[0]);i++)if(unsetenv(old[i])!=0)_exit(94);
        if(!ffr3_set_native_home())_exit(94);
        execl(python,python,"-I","-B","-c",script,(char*)NULL);_exit(95);
    }
    free(script);close(channel[0]);s->grant_writer=channel[1];s->fork_return_ns=ffr3_now_ns();if(!ffr3_budget(&s->prepared->stop)||s->fork_return_ns<s->fork_enter_ns){close(s->grant_writer);s->grant_writer=-1;return NULL;}int slots=ffr3_child_directory(s->prepared->root,"slots"),slotfd=slots>=0?ffr3_child_directory(slots,s->slot):-1;
    char *identity=NULL;size_t bytes=0;
    while(slotfd>=0&&ffr3_budget(&s->prepared->stop)){
        int locked=flock(slotfd,LOCK_SH|LOCK_NB)==0;
        if(locked){
            struct stat metadata;int found=fstatat(slotfd,"child-identity",&metadata,AT_SYMLINK_NOFOLLOW)==0,saved=errno;
            if(found)identity=ffr3_capture_at(slotfd,"child-identity",FFR3_MAX_RECORD,&bytes,1,&s->prepared->stop);
            if(flock(slotfd,LOCK_UN)!=0){free(identity);identity=NULL;break;}
            if(found||saved!=ENOENT)break;
        }else if(errno!=EWOULDBLOCK&&errno!=EAGAIN)break;
        int status=0;pid_t state=waitpid(child,&status,WNOHANG);if(state==child||state<0)break;struct timespec pause={0,1000000};nanosleep(&pause,NULL);
    }
    if(slotfd>=0)close(slotfd);if(slots>=0)close(slots);char *body=identity?ffr3_json_field(identity,"payload"):NULL,*process=body?ffr3_json_field(body,"child"):NULL,*parent=body?ffr3_json_field(body,"parent"):NULL;
    char actual_pid[32],pid[32],nonce[65];snprintf(actual_pid,sizeof(actual_pid),"%ld",(long)child);int valid=identity&&ffr3_native_verify(&s->codec,identity,0)&&process&&parent&&!strcmp(parent,s->prepared->controller)&&ffr3_json_string_value(process,"pid",pid,sizeof(pid))&&!strcmp(pid,actual_pid)&&ffr3_json_string_value(body,"child_nonce",nonce,sizeof(nonce))&&!strcmp(nonce,s->nonce);
    struct proc_bsdinfo observed;memset(&observed,0,sizeof(observed));if(valid)valid=proc_pidinfo(child,PROC_PIDTBSDINFO,0,&observed,sizeof(observed))==(int)sizeof(observed);
    char *birth=process?ffr3_json_field(process,"kernel_birth"):NULL;char seconds[32],microseconds[32];if(valid)valid=birth&&ffr3_json_string_value(birth,"seconds",seconds,sizeof(seconds))&&ffr3_json_string_value(birth,"microseconds",microseconds,sizeof(microseconds))&&strtoull(seconds,NULL,10)==observed.pbi_start_tvsec&&strtoull(microseconds,NULL,10)==observed.pbi_start_tvusec;
    if(valid)s->child_process=strdup(process);
    char *result=valid?ffr3_format("{\"child\":%s,\"fork_enter_ns\":\"%llu\",\"fork_return_ns\":\"%llu\",\"ready_deadline_ns\":\"%llu\"}",process,s->fork_enter_ns,s->fork_return_ns,s->fork_enter_ns+120000000000ULL):NULL;
    free(identity);free(body);free(process);free(parent);free(birth);return result;
}
static char *ffr3_record_ref(const char *raw);
static char *ffr3_native_send_grant(FFR3Session *s,const char *payload) {
    if(!s->fork_spent||s->grant_spent||!s->product||s->grant_writer<0||!s->started||!ffr3_budget(&s->prepared->stop))return NULL;s->grant_spent=1;
    char *parent=ffr3_json_field(payload,"parent"),*intent=ffr3_json_field(payload,"intent"),*started=ffr3_json_field(payload,"child_started");
    char nonce[65],slot[65],deadline[32];int valid=parent&&!strcmp(parent,s->prepared->controller)&&intent&&started&&ffr3_json_string_value(payload,"child_nonce",nonce,sizeof(nonce))&&!strcmp(nonce,s->nonce)&&ffr3_json_string_value(payload,"slot",slot,sizeof(slot))&&!strcmp(slot,s->slot)&&ffr3_json_string_value(payload,"stop_deadline_ns",deadline,sizeof(deadline));
    unsigned long long origin=(unsigned long long)s->prepared->origin.tv_sec*1000000000ULL+(unsigned long long)s->prepared->origin.tv_nsec;if(valid)valid=strtoull(deadline,NULL,10)==origin+15000000000ULL;
    char *expected_intent=s->intent?ffr3_record_ref(s->intent):NULL,*expected_started=ffr3_record_ref(s->started),
        *child=ffr3_json_field(payload,"child"),*capability=ffr3_json_field(payload,"controller_capability"),*expected_capability=ffr3_evidence(s->capability);
    char ready[32],gate[32],identity[32],durable[32];unsigned long long now=ffr3_now_ns();
    if(valid)valid=expected_intent&&expected_started&&child&&s->child_process&&capability&&expected_capability&&
        !strcmp(intent,expected_intent)&&!strcmp(started,expected_started)&&!strcmp(child,s->child_process)&&!strcmp(capability,expected_capability)&&
        ffr3_json_string_value(payload,"ready_deadline_ns",ready,sizeof(ready))&&strtoull(ready,NULL,10)==s->fork_enter_ns+120000000000ULL&&
        ffr3_json_string_value(payload,"gate_ns",gate,sizeof(gate))&&ffr3_json_string_value(payload,"identity_verified_ns",identity,sizeof(identity))&&
        ffr3_json_string_value(payload,"child_started_durable_ns",durable,sizeof(durable))&&
        s->fork_return_ns<=strtoull(durable,NULL,10)&&strtoull(durable,NULL,10)<=strtoull(identity,NULL,10)&&
        strtoull(identity,NULL,10)<=strtoull(gate,NULL,10)&&strtoull(gate,NULL,10)<=now;
    char *raw=valid?malloc(8193):NULL;size_t size=raw?ffr3_native_encode(&s->codec,"COMPOSITION_AUTHORITY",0,payload,strtoull(gate,NULL,10),raw,8193):0;
    if(size)valid=failed_fenced_send_frame(s->grant_writer,(const unsigned char*)raw,size,&s->prepared->stop);else{close(s->grant_writer);valid=0;}s->grant_writer=-1;
    free(parent);free(intent);free(started);free(raw);free(expected_intent);free(expected_started);free(child);free(capability);free(expected_capability);if(!valid)return NULL;
    return ffr3_format("{\"fork_enter_ns\":\"%llu\",\"ready_deadline_ns\":\"%llu\",\"sent_ns\":\"%llu\"}",s->fork_enter_ns,s->fork_enter_ns+120000000000ULL,ffr3_now_ns());
}

static const struct timespec *ffr3_session_deadline(const FFR3Session *s) {return s->grant_spent?&s->ready_deadline:&s->prepared->stop;}
static char *ffr3_record_ref(const char *raw) {
    char kind[96],hash[65];unsigned char bytes[32];if(!ffr3_json_string_value(raw,"kind",kind,sizeof(kind)))return NULL;
    CC_SHA256(raw,(CC_LONG)strlen(raw),bytes);ffr3_hex(bytes,hash);return ffr3_format("{\"hash\":\"%s\",\"kind\":\"%s\"}",hash,kind);
}
static char *ffr3_ready_evidence(const char *raw) {
    char *evidence=ffr3_evidence(raw);if(!evidence)return NULL;char *old=strstr(evidence,"\"LAUNCHER\"");
    if(!old){free(evidence);return NULL;}char *result=ffr3_format("%.*s\"SUCCESSOR\"%s",(int)(old-evidence),evidence,old+10);free(evidence);return result;
}
static char *ffr3_native_wait_ready(FFR3Session *s) {
    if(!s->grant_spent||!s->started||!s->child_process||s->ready_payload)return NULL;
    /* Actual signed S publications only. This loop cannot trigger restoration,
     * resend a grant, re-fork, repair a record or create another process. */
    char prefix[128];snprintf(prefix,sizeof(prefix),"ready-%s",s->nonce);char *restoration=NULL,*source=NULL,*capability=NULL,*provider=NULL,*transport=NULL;
    while(ffr3_budget(&s->ready_deadline)){
        const char *kinds[]={"RESTORATION","SOURCE","CAPABILITY","ABSENCE","ABSENCE"};
        const char *labels[]={"restoration","source","capability","absence-PROVIDER","absence-MARKET_TRANSPORT"};
        char **values[]={&restoration,&source,&capability,&provider,&transport};int complete=1;
        for(size_t i=0;i<5;i++)if(!*values[i]){
            char identity[256];snprintf(identity,sizeof(identity),"%s-%s",prefix,labels[i]);
            *values[i]=ffr3_find_proof(s,kinds[i],identity,s->child_process);if(!*values[i])complete=0;
        }
        if(complete)break;int status=0;pid_t observed=waitpid(s->product,&status,WNOHANG);if(observed==s->product||observed<0)break;
        struct timespec pause={0,1000000};nanosleep(&pause,NULL);
    }
    char *rest=restoration?ffr3_json_field(restoration,"payload"):NULL,*startup_ref=rest?ffr3_json_field(rest,"startup_context"):NULL;
    char *startup_raw=NULL;char kind[96],hash[65],name[180];size_t bytes=0;
    if(startup_ref&&ffr3_json_string_value(startup_ref,"kind",kind,sizeof(kind))&&!strcmp(kind,"STARTUP_CONTEXT")&&ffr3_json_string_value(startup_ref,"hash",hash,sizeof(hash))){snprintf(name,sizeof(name),"%s-%s.json",kind,hash);startup_raw=ffr3_capture_at(s->prepared->records,name,FFR3_MAX_RECORD,&bytes,1,&s->ready_deadline);}
    char *startup=startup_raw?ffr3_json_field(startup_raw,"payload"):NULL,*consumption=startup?ffr3_json_field(startup,"consumption"):NULL,*guard=NULL;
    char *intent=s->intent?ffr3_json_field(s->intent,"payload"):NULL,*transaction=intent?ffr3_json_field(intent,"transaction"):NULL,*owner=intent?ffr3_json_field(intent,"execution_owner"):NULL;
    int slots=ffr3_child_directory(s->prepared->root,"slots"),slotfd=slots>=0?ffr3_child_directory(slots,s->slot):-1;
    char *claim=slotfd>=0?ffr3_capture_at(slotfd,"claim",FFR3_MAX_RECORD,&bytes,1,&s->ready_deadline):NULL,*claim_payload=claim?ffr3_json_field(claim,"payload"):NULL;
    if(claim_payload)guard=ffr3_json_field(claim_payload,"guard");if(slotfd>=0)close(slotfd);if(slots>=0)close(slots);
    char *intent_ref=s->intent?ffr3_record_ref(s->intent):NULL,*started_ref=ffr3_record_ref(s->started),*e_rest=restoration?ffr3_ready_evidence(restoration):NULL,*e_source=source?ffr3_ready_evidence(source):NULL,*e_cap=capability?ffr3_ready_evidence(capability):NULL,*e_provider=provider?ffr3_ready_evidence(provider):NULL,*e_transport=transport?ffr3_ready_evidence(transport):NULL;
    int valid=rest&&source&&capability&&provider&&transport&&startup_raw&&ffr3_native_verify(&s->codec,startup_raw,0)&&consumption&&guard&&transaction&&owner&&intent_ref&&started_ref&&e_rest&&e_source&&e_cap&&e_provider&&e_transport&&ffr3_budget(&s->ready_deadline);
    char *result=valid?ffr3_format("{\"payload\":{\"capability\":%s,\"child_started\":%s,\"consumption\":%s,\"execution_owner\":%s,\"guard\":%s,\"intent\":%s,\"provider_absence\":%s,\"ready_ns\":\"%llu\",\"restoration\":%s,\"runtime\":%s,\"slot\":\"%s\",\"source\":%s,\"startup\":%s,\"transaction\":%s,\"transport_absence\":%s}}",e_cap,started_ref,consumption,owner,guard,intent_ref,e_provider,ffr3_now_ns(),e_rest,s->child_process,s->slot,e_source,startup_ref,transaction,e_transport):NULL;
    if(result)s->ready_payload=ffr3_json_field(result,"payload");
    free(restoration);free(source);free(capability);free(provider);free(transport);free(rest);free(startup_ref);free(startup_raw);free(startup);free(consumption);free(intent);free(transaction);free(owner);free(claim);free(claim_payload);free(guard);free(intent_ref);free(started_ref);free(e_rest);free(e_source);free(e_cap);free(e_provider);free(e_transport);return result;
}

/* Unsigned preflight facts use only the existing closed payload shapes. The
 * exact qualified original helper supplies these after native validation;
 * retention creates no L proof, approval, operation or launch right. */
static int ffr3_fact_payload(const char *kind,const char *payload) {
    RecoveryJson *j=calloc(1,sizeof(*j));if(!j)return 0;int valid=ffr3_canonical_object(j,payload);
    static const char *target[]={"approval","bootstrap_plan","capability_manifest","configuration","identity","interface","package","restoration_plan","revision","scope","service","source_inventory"};
    static const char *package[]={"artifact_approval","executable","identity","manifest","role","signature","verified_ns"};
    static const char *compatibility[]={"acceptance","configuration","epoch","identity","mode","predecessor","relation","successor","verified_ns","window"};
    const char **fields=NULL;size_t count=0;
    if(!strcmp(kind,"TARGET_ARTIFACT")){fields=target;count=sizeof(target)/sizeof(target[0]);}
    else if(!strcmp(kind,"PACKAGE")){fields=package;count=sizeof(package)/sizeof(package[0]);}
    else if(!strcmp(kind,"COMPATIBILITY")){fields=compatibility;count=sizeof(compatibility)/sizeof(compatibility[0]);}
    if(!fields||!valid||j->token[0].count!=(int)count)valid=0;
    for(size_t i=0;valid&&i<count;i++)valid=recovery_json_get(j,0,fields[i])>=0;
    char identity[256];if(valid)valid=recovery_string(j,0,"identity",identity,sizeof(identity))&&ffr3_id(identity);
    if(valid&&strcmp(kind,"TARGET_ARTIFACT")){
        char verified[32];valid=recovery_string(j,0,"verified_ns",verified,sizeof(verified))&&strspn(verified,"0123456789")==strlen(verified)&&
            (verified[0]!='0'||!verified[1])&&strtoull(verified,NULL,10)<=ffr3_now_ns();
    }
    free(j);return valid;
}
static char *ffr3_broker_fact(FFR3Session *s,const char *proposal) {
    if(strcmp(s->prepared->mode,"\"ORIGINAL\"")||s->shutdown_sent||s->original_reserved||s->fork_spent||s->grant_spent||!ffr3_budget(&s->prepared->stop))return NULL;
    RecoveryJson *j=calloc(1,sizeof(*j));char kind[96],*payload=NULL,*result=NULL;
    if(!j||!ffr3_private_call_object(j,proposal)||j->token[0].count!=2||!recovery_string(j,0,"kind",kind,sizeof(kind)))goto done;
    payload=ffr3_json_value(j,recovery_json_get(j,0,"payload"));if(!payload||!ffr3_fact_payload(kind,payload))goto done;
    char identity[256],hash[65],name[80];if(!ffr3_json_string_value(payload,"identity",identity,sizeof(identity)))goto done;
    char *ref=ffr3_blob_ref(identity,payload);int valid=ref&&ffr3_json_string_value(ref,"hash",hash,sizeof(hash));
    if(valid){snprintf(name,sizeof(name),"%s.blob",hash);valid=ffr3_publish_immutable(s->prepared->blobs,name,payload,strlen(payload),&s->prepared->stop);}
    if(valid&&s->fact_count<4){s->fact_refs[s->fact_count++]=strdup(ref);result=ffr3_format("{\"fact\":%s}",ref);}free(ref);
 done:free(j);free(payload);return result;
}

static char *ffr3_broker_publish(FFR3Session *s,const char *proposal,int reserve) {
    RecoveryJson *j=calloc(1,sizeof(*j));char kind[96],*payload=NULL,*result=NULL;int external=0;
    if(!j||!ffr3_private_call_object(j,proposal)||j->token[0].count!=3||!recovery_string(j,0,"kind",kind,sizeof(kind))||
       !ffr3_canonical_boolean(j,recovery_json_get(j,0,"external"),&external))goto done;
    payload=ffr3_json_value(j,recovery_json_get(j,0,"payload"));if(!payload)goto done;
    /* The source-pinned helper checks full closed graph semantics. Native C
     * independently narrows issuance to this phase and actual fixed lineage,
     * slot, clock, single attempt and finite irreversible transitions. */
    if(!strcmp(s->prepared->mode,"\"ORIGINAL\""))goto done;
    if(external){
        if(reserve||strcmp(kind,"RECOVERY_AUTHORITY"))goto done;
        char *controller=ffr3_json_field(payload,"controller");if(controller){free(controller);goto done;}
        char *lineage=ffr3_json_field(payload,"lineage");int same=lineage&&!strcmp(lineage,s->prepared->lineage);free(lineage);if(!same)goto done;
    }else if(reserve){
        if(strcmp(kind,"GUARD")&&strcmp(kind,"CLAIM")&&strcmp(kind,"CHILD_INTENT"))goto done;
        if((!strcmp(kind,"GUARD")&&s->guard_reserved)||(!strcmp(kind,"CLAIM")&&(!s->guard_reserved||s->claim_reserved))||
           (!strcmp(kind,"CHILD_INTENT")&&(!s->claim_reserved||s->intent_reserved||s->fork_spent)))goto done;
    }else if(strcmp(kind,"OBSERVATION")&&strcmp(kind,"EXIT_PROOF")&&strcmp(kind,"CHILD_STARTED")&&strcmp(kind,"READY_RECEIPT")&&strcmp(kind,"FAILURE"))goto done;
    char slot[65];if(!ffr3_json_string_value(payload,"slot",slot,sizeof(slot))||!valid_token(slot))goto done;
    if(*s->slot&&strcmp(s->slot,slot))goto done;if(!*s->slot)strcpy(s->slot,slot);
    if(!strcmp(kind,"OBSERVATION")&&!s->ack)goto done;
    if(!strcmp(kind,"EXIT_PROOF")&&!s->ack)goto done;
    if(!strcmp(kind,"READY_RECEIPT")&&(!s->grant_spent||!s->product||!s->ready_payload||s->ready_receipt||strcmp(payload,s->ready_payload)))goto done;
    if(s->grant_spent&&strcmp(kind,"READY_RECEIPT"))goto done;
    if(!strcmp(kind,"CHILD_STARTED")){
        char *child=ffr3_json_field(payload,"child"),*parent=ffr3_json_field(payload,"parent");
        int same=s->fork_spent&&!s->started&&child&&parent&&s->child_process&&!strcmp(child,s->child_process)&&!strcmp(parent,s->prepared->controller);
        free(child);free(parent);if(!same)goto done;
    }
    unsigned long long now=ffr3_now_ns();char *raw=NULL;
    if(!strcmp(kind,"READY_RECEIPT")){
        raw=malloc(FFR3_MAX_RECORD+1);char digest[65];
        if(!raw||!ffr3_budget(&s->ready_deadline)||!ffr3_native_encode(&s->codec,kind,0,payload,now,raw,FFR3_MAX_RECORD+1)||!ffr3_publish_record(s->prepared->records,&s->codec,raw,kind,0,&s->ready_deadline,digest)){free(raw);raw=NULL;}
    }else if(reserve){
        raw=malloc(FFR3_MAX_RECORD+1);
        if(!raw||!ffr3_native_encode(&s->codec,kind,0,payload,now,raw,FFR3_MAX_RECORD+1)){free(raw);raw=NULL;}
    }else raw=ffr3_signed_publish(s->prepared,&s->codec,kind,external,payload,now);
    if(!raw)goto done;
    if(!strcmp(kind,"READY_RECEIPT"))s->ready_receipt=ffr3_record_ref(raw);
    if(!strcmp(kind,"CHILD_STARTED")){s->started=strdup(raw);if(!s->started){free(raw);goto done;}}
    if(reserve){
        int parent=ffr3_child_directory(s->prepared->root,!strcmp(kind,"GUARD")?"guards":"slots"),slotfd=-1;
        int valid=parent>=0;
        if(!strcmp(kind,"GUARD")){
            valid=valid&&mkdirat(parent,slot,0700)==0&&fsync(parent)==0;
            if(valid)slotfd=ffr3_child_directory(parent,slot);
            valid=valid&&slotfd>=0&&ffr3_publish_immutable(slotfd,"guard",raw,strlen(raw),&s->prepared->stop);
            if(valid)s->guard_reserved=1;
        }
        else{
            if(!strcmp(kind,"CLAIM")){valid=valid&&mkdirat(parent,slot,0700)==0&&fsync(parent)==0;}
            if(valid)slotfd=ffr3_child_directory(parent,slot);valid=valid&&slotfd>=0;
            const char *fixed=!strcmp(kind,"CLAIM")?"claim":"child-intent";
            if(valid)valid=ffr3_publish_immutable(slotfd,fixed,raw,strlen(raw),&s->prepared->stop);
            if(valid&&!strcmp(kind,"CLAIM"))s->claim_reserved=1;
            if(valid&&!strcmp(kind,"CHILD_INTENT")){s->intent_reserved=1;s->intent=strdup(raw);valid=s->intent&&ffr3_json_string_value(payload,"child_nonce",s->nonce,sizeof(s->nonce))&&valid_token(s->nonce);}
        }
        if(slotfd>=0)close(slotfd);if(parent>=0)close(parent);if(!valid){free(raw);goto done;}
    }
    char *hex=ffr3_bytes_hex(raw,strlen(raw));if(hex)result=ffr3_format("{\"raw\":\"%s\"}",hex);free(hex);free(raw);
 done:free(payload);free(j);return result;
}
static char *ffr3_broker_probe(FFR3Session *s,const char *payload) {
    char kind[96];char *subject=ffr3_json_field(payload,"subject");if(!subject||!ffr3_json_string_value(payload,"kind",kind,sizeof(kind))){free(subject);return NULL;}
    char *predecessor=ffr3_json_field(s->prepared->lineage,"predecessor");int allowed=predecessor&&!strcmp(predecessor,subject)&&
       (!strcmp(kind,"PROCESS_BIRTH")||!strcmp(kind,"PROCESS_EXIT")||!strcmp(kind,"LISTENER_ABSENT"));free(predecessor);
    if(!strcmp(kind,"CANONICAL_PARENT")&&!strcmp(subject,s->prepared->controller))allowed=1;
    char *raw=allowed?((!strcmp(kind,"PROCESS_BIRTH")||!strcmp(kind,"PROCESS_EXIT"))?ffr3_native_process_proof(s,subject,kind):ffr3_native_other_probe(s,subject,kind)):NULL;free(subject);
    char *hex=raw?ffr3_bytes_hex(raw,strlen(raw)):NULL,*result=hex?ffr3_format("{\"raw\":\"%s\"}",hex):NULL;free(hex);free(raw);return result;
}
static char *ffr3_broker_request(FFR3Session *s,const char *request) {
    RecoveryJson *j=calloc(1,sizeof(*j));char context[65],sequence[32],kind[96];char *payload=NULL,*result=NULL;
    if(!j||!ffr3_private_call_object(j,request)||j->token[0].count!=4||!recovery_string(j,0,"context",context,sizeof(context))||strcmp(context,s->context_hash)||
       !recovery_string(j,0,"sequence",sequence,sizeof(sequence))||!recovery_string(j,0,"kind",kind,sizeof(kind)))goto done;
    char actual[32];snprintf(actual,sizeof(actual),"%llu",s->sequence);if(strcmp(actual,sequence)||s->sequence>=4096||s->done)goto done;
    s->sequence++;payload=ffr3_json_value(j,recovery_json_get(j,0,"payload"));if(!payload)goto done;
    if(s->read_only&&strcmp(kind,"VERIFY")&&strcmp(kind,"DONE"))goto done;
    if(!strcmp(kind,"VERIFY"))result=ffr3_broker_verify(s,payload);
    else if(!strcmp(kind,"PUBLISH"))result=ffr3_broker_publish(s,payload,0);
    else if(!strcmp(kind,"FACT"))result=ffr3_broker_fact(s,payload);
    else if(!strcmp(kind,"RESERVE"))result=ffr3_broker_publish(s,payload,1);
    else if(!strcmp(kind,"PROBE")&&!s->grant_spent)result=ffr3_broker_probe(s,payload);
    else if(!strcmp(kind,"EXCHANGE")&&!s->grant_spent&&!strcmp(payload,"{}"))result=ffr3_native_exchange(s);
    else if(!strcmp(kind,"FORK")&&!s->grant_spent&&!strcmp(payload,"{}"))result=ffr3_native_fork(s);
    else if(!strcmp(kind,"SEND_GRANT")&&!s->grant_spent)result=ffr3_native_send_grant(s,payload);
    else if(!strcmp(kind,"WAIT_READY")&&s->grant_spent&&!strcmp(payload,"{}"))result=ffr3_native_wait_ready(s);
    else if(!strcmp(kind,"DONE")){
        int allowed=!s->grant_spent&&(!strcmp(s->prepared->mode,"\"ORIGINAL\"")||s->read_only)&&!strcmp(payload,"{}");
        if(s->grant_spent&&s->ready_receipt){char *ready=ffr3_json_field(payload,"ready");allowed=ready&&!strcmp(ready,s->ready_receipt);free(ready);}
        if(allowed){s->done=1;result=strdup("{\"returned\":true}");}
    }
    if(result){char *response=ffr3_format("{\"context\":\"%s\",\"kind\":\"%s\",\"result\":%s,\"sequence\":\"%s\"}",s->context_hash,kind,result,sequence);free(result);result=response;}
 done:free(payload);free(j);return result;
}
static int ffr3_run_broker(FFR3Session *s,const char *python,const char *pin_frame,size_t pin_bytes,const char *context) {
    if(s->helper||!ffr3_budget(&s->prepared->stop))return 0;int input[2],output[2];
    if(!failed_fenced_pipe(input))return 0;if(!failed_fenced_pipe(output)){close(input[0]);close(input[1]);return 0;}
    char origin[32],stop[32];unsigned long long started=(unsigned long long)s->prepared->origin.tv_sec*1000000000ULL+(unsigned long long)s->prepared->origin.tv_nsec;
    snprintf(origin,sizeof(origin),"%llu",started);snprintf(stop,sizeof(stop),"%llu",started+15000000000ULL);
    pid_t child=fork();s->helper=child;if(child<0){close(input[0]);close(input[1]);close(output[0]);close(output[1]);return 0;}
    if(!child){
        if(dup2(input[0],0)!=0||dup2(output[1],1)!=1)_exit(91);int null=open("/dev/null",O_WRONLY);if(null<0||dup2(null,2)!=2)_exit(92);
        int maximum=getdtablesize();for(int fd=3;fd<maximum;fd++)if(close(fd)!=0&&errno!=EBADF)_exit(93);
        if(!ffr3_set_native_home())_exit(93);
        execl(python,python,"-I","-B","-S","-c",ffr3_pin_bootstrap,origin,stop,(char*)NULL);_exit(94);
    }
    close(input[0]);close(output[1]);char *actual=NULL;int valid=ffr3_helper_context(context,child,&actual);unsigned char digest[32];
    if(valid){CC_SHA256(actual,(CC_LONG)strlen(actual),digest);ffr3_hex(digest,s->context_hash);}
    struct sigaction ignore={0},previous={0};ignore.sa_handler=SIG_IGN;int changed=sigaction(SIGPIPE,&ignore,&previous)==0;valid=valid&&changed;
    if(valid)valid=ffr3_helper_frame(input[1],pin_frame,pin_bytes,64U*1024U*1024U,&s->prepared->stop)&&
        ffr3_helper_frame(input[1],actual,strlen(actual),FFR3_MAX_RECORD,&s->prepared->stop);
    if(valid){free(s->helper_process);s->helper_process=ffr3_json_field(actual,"helper");valid=s->helper_process!=NULL;}
    free(actual);
    while(valid&&!s->done){char *request=ffr3_read_frame(output[0],4U*FFR3_MAX_RECORD,ffr3_session_deadline(s));
        char *response=request?ffr3_broker_request(s,request):NULL;free(request);
        valid=response&&ffr3_helper_frame(input[1],response,strlen(response),4U*FFR3_MAX_RECORD,ffr3_session_deadline(s));free(response);}
    close(input[1]);if(changed)(void)sigaction(SIGPIPE,&previous,NULL);
    if(valid){char extra;valid=recovery_wait_io(output[0],POLLIN,ffr3_session_deadline(s))&&read(output[0],&extra,1)==0;}close(output[0]);
    int status=0;pid_t joined;do{joined=waitpid(child,&status,0);}while(joined<0&&errno==EINTR);s->helper_joined=joined==child;
    return valid&&s->done&&s->helper_joined&&WIFEXITED(status)&&WEXITSTATUS(status)==0&&ffr3_budget(ffr3_session_deadline(s));
}

typedef struct FailedFencedNativeStart {
    const char *repository,*python,*entry,*python_path,*slot,*nonce;
    struct timespec stop_deadline;
    /* Source-qualified internal adapters validate/publish the exact R3 graph;
     * request data never supplies executable callbacks or command strings. */
    int (*reserve_intent)(void *state);
    int (*observe_and_publish_started)(void *state,pid_t child,const struct timespec *fork_enter,
                                      const struct timespec *fork_return,const struct timespec *ready_deadline);
    int (*build_one_grant)(void *state,unsigned char bytes[8192],size_t *length);
    int (*retain_ready_receipt)(void *state,pid_t child,const struct timespec *ready_deadline);
    void *state;
    BackendStartMonitor monitor;
} FailedFencedNativeStart;

static BackendStartResult __attribute__((unused)) start_failed_fenced_backend(FailedFencedNativeStart *plan) {
    if(!plan || !plan->reserve_intent || !plan->observe_and_publish_started ||
       !plan->build_one_grant || !plan->retain_ready_receipt || !plan->repository ||
       !plan->python || !plan->entry || !plan->python_path || !valid_token(plan->slot) ||
       !valid_token(plan->nonce))return BACKEND_START_INTERNAL_FAILURE;
    struct timespec now;
    if(clock_gettime(CLOCK_MONOTONIC,&now)!=0 || time_reached(&now,&plan->stop_deadline) ||
       !plan->reserve_intent(plan->state))return BACKEND_START_INTERNAL_FAILURE;
    int channel[2];if(!failed_fenced_pipe(channel))return BACKEND_START_INTERNAL_FAILURE;
    struct timespec fork_enter;
    if(clock_gettime(CLOCK_MONOTONIC,&fork_enter)!=0 || time_reached(&fork_enter,&plan->stop_deadline)){
        close(channel[0]);close(channel[1]);return BACKEND_START_INTERNAL_FAILURE;
    }
    struct timespec ready_deadline=fork_enter;ready_deadline.tv_sec+=120;
    pid_t child=fork(); /* the sole product child; intent is already spent */
    if(child<0){close(channel[0]);close(channel[1]);return BACKEND_START_INTERNAL_FAILURE;}
    if(child==0){
        if(!failed_fenced_child_descriptor(channel[0],channel[1]) || setsid()<0)_exit(1);
        int devnull=open("/dev/null",O_RDWR);
        if(devnull<0)_exit(1);
        if(dup2(devnull,STDIN_FILENO)<0 || dup2(devnull,STDOUT_FILENO)<0 || dup2(devnull,STDERR_FILENO)<0)_exit(1);
        if(devnull>3)close(devnull);
        if(chdir(plan->repository)!=0 || setenv("PYTHONPATH",plan->python_path,1)!=0 ||
           setenv("KRONOS_FAILED_FENCED_RECOVERY_VERSION","1.0.0",1)!=0 ||
           setenv("KRONOS_FAILED_FENCED_RECOVERY_SLOT",plan->slot,1)!=0 ||
           setenv("KRONOS_FAILED_FENCED_RECOVERY_CHILD_NONCE",plan->nonce,1)!=0)_exit(1);
        const char *forbidden[]={"KRONOS_MAINTENANCE_GENERATION","KRONOS_MAINTENANCE_PARENT",
            "KRONOS_MAINTENANCE_PROOF","KRONOS_MAINTENANCE_PROTOCOL","KRONOS_MAINTENANCE_REVISION",
            "KRONOS_LEGACY_BOOTSTRAP_ID","KRONOS_LEGACY_BOOTSTRAP_PROOF","KRONOS_LAUNCH_MODE",
            "KRONOS_REPLACEMENT_REVISION","KRONOS_RECOVERY_ATTEMPT"};
        for(size_t i=0;i<sizeof(forbidden)/sizeof(forbidden[0]);i++)if(unsetenv(forbidden[i])!=0)_exit(1);
        execl(plan->python,plan->python,"-B",plan->entry,"--no-browser",(char*)NULL);_exit(1);
    }
    close(channel[0]);
    struct timespec fork_return;
    if(clock_gettime(CLOCK_MONOTONIC,&fork_return)!=0 || time_reached(&fork_return,&plan->stop_deadline) ||
       !plan->observe_and_publish_started(plan->state,child,&fork_enter,&fork_return,&ready_deadline)){
        close(channel[1]);return BACKEND_START_INTERNAL_FAILURE;
    }
    unsigned char grant[8192];size_t length=0;
    if(!plan->build_one_grant(plan->state,grant,&length)){
        close(channel[1]);return BACKEND_START_INTERNAL_FAILURE;
    }
    if(!failed_fenced_send_frame(channel[1],grant,length,&plan->stop_deadline))return BACKEND_START_INTERNAL_FAILURE;
    BackendStartResult result=monitor_failed_fenced_start(child,&ready_deadline,&plan->monitor);
    if(result==BACKEND_START_READY && !plan->retain_ready_receipt(plan->state,child,&ready_deadline))
        return BACKEND_START_INTERNAL_FAILURE;
    return result;
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
    /* A capable executable never infers LEGACY_UNENROLLED from an absent
     * estate. The exact approved static bootstrap runs before every excluded
     * tool/root import and independently verifies the guard before owners. */
    if (!browser_entry || access(browser_entry, R_OK) != 0) return BACKEND_START_INTERNAL_FAILURE;
    FFR3PreparedNative native_startup;
    char *pinned_script = ffr3_ordinary_pin_script(repository,python,&native_startup);
    if (pinned_script == NULL) return BACKEND_START_INTERNAL_FAILURE;
    pid_t child = fork();
    if (child < 0) { free(pinned_script);ffr3_release_preparation(&native_startup); return BACKEND_START_INTERNAL_FAILURE; }
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
        if(!ffr3_set_native_home())_exit(1);
        execl(python, python, "-I", "-B", "-c", pinned_script, (char *)NULL);
        _exit(1);
    }
    free(pinned_script);
    BackendStartMonitor monitor=production_backend_start_monitor;
    if(recovery_successor.authority){
        recovery_successor.child=child;monitor.ready=recovery_successor_ready;
        if(monotonic_now(&recovery_successor.deadline)!=0){ffr3_release_preparation(&native_startup);return BACKEND_START_INTERNAL_FAILURE;}
        recovery_successor.deadline.tv_sec+=BACKEND_START_READY_TIMEOUT_SECONDS;
        recovery_io_deadline=&recovery_successor.deadline;
    }
    BackendStartResult result=monitor_backend_start(
        child,
        BACKEND_START_READY_TIMEOUT_SECONDS,
        &monitor
    );
    recovery_io_deadline=NULL;
    ffr3_release_preparation(&native_startup);
    return result;
}

static char *ffr3_current_record(FFR3Session *s,const char *kind) {
    DIR *directory=ffr3_directory_stream(s->prepared->records);if(!directory)return NULL;struct dirent *entry;char *result=NULL;size_t seen=0,bytes=0;int valid=1;
    while(valid&&(entry=readdir(directory))){const char *name=entry->d_name;if(!strcmp(name,".")||!strcmp(name,".."))continue;
        if(++seen>4096){valid=0;break;}if(strncmp(name,kind,strlen(kind))||name[strlen(kind)]!='-')continue;
        size_t n=0;char *raw=ffr3_capture_at(s->prepared->records,name,FFR3_MAX_RECORD,&n,1,&s->prepared->stop);if(!raw||bytes+n>64U*1024U*1024U){free(raw);valid=0;break;}bytes+=n;
        char *payload=ffr3_json_field(raw,"payload"),*lineage=payload?ffr3_json_field(payload,"lineage"):NULL;
        if(lineage&&!strcmp(lineage,s->prepared->lineage)&&ffr3_native_verify(&s->codec,raw,0)){
            unsigned char digest[32];char hash[65],expected[180];CC_SHA256(raw,(CC_LONG)n,digest);ffr3_hex(digest,hash);snprintf(expected,sizeof(expected),"%s-%s.json",kind,hash);
            if(strcmp(expected,name)||result){valid=0;}else{result=raw;raw=NULL;}
        }
        free(payload);free(lineage);free(raw);
    }
    closedir(directory);if(!valid){free(result);return NULL;}return result;
}
static char *ffr3_wait_current_record(FFR3Session *s,const char *kind) {
    while(ffr3_budget(&s->prepared->stop)){char *raw=ffr3_current_record(s,kind);if(raw)return raw;struct timespec pause={0,1000000};nanosleep(&pause,NULL);}return NULL;
}
static char *ffr3_original_closure(FFR3Session *s,unsigned long long *closed_ns) {
    if(!s->helper_joined||!s->original_reserved||s->fork_spent||!s->count)return NULL;
    char *admissions=ffr3_array_refs(s->admissions,s->count),*dispatches=ffr3_array_refs(s->dispatches,s->count);
    char *cap=ffr3_json_field(s->capability,"payload"),*lock=cap?ffr3_json_field(cap,"execution_lock"):NULL;
    char *identity_input=ffr3_format("{\"attempt\":%s,\"controller\":%s}",s->prepared->attempt,s->prepared->controller);unsigned char digest[32];char identity[65];
    if(identity_input){CC_SHA256(identity_input,(CC_LONG)strlen(identity_input),digest);ffr3_hex(digest,identity);}*closed_ns=ffr3_now_ns();
    const char *rights="[{\"kind\":\"CHILD_FORK\",\"state\":\"CLOSED_UNUSED\"},{\"kind\":\"CHILD_INTENT\",\"state\":\"CLOSED_UNUSED\"},{\"kind\":\"CONSUME\",\"state\":\"CLOSED_UNUSED\"},{\"kind\":\"RELEASE_COMPOSITION\",\"state\":\"CLOSED_UNUSED\"}]";
    char *payload=admissions&&dispatches&&lock&&identity_input?ffr3_format("{\"admissions\":%s,\"attempt\":%s,\"capability\":%s,\"closed_ns\":\"%llu\",\"controller\":%s,\"dispatch_heads\":%s,\"execution_lock\":%s,\"identity\":\"controller-closure-%s\",\"lineage\":%s,\"outstanding\":\"0\",\"publisher\":\"native-controller\",\"publisher_owners\":\"1\",\"rights\":%s}",admissions,s->prepared->attempt,s->capability_ref,*closed_ns,s->prepared->controller,dispatches,lock,identity,s->prepared->lineage,rights):NULL;
    char *raw=payload?ffr3_signed_publish(s->prepared,&s->codec,"CONTROLLER_CLOSURE",1,payload,*closed_ns):NULL;
    free(admissions);free(dispatches);free(cap);free(lock);free(identity_input);free(payload);return raw;
}
static int ffr3_close_original(FFR3Session *s) {
    char *terminal=ffr3_wait_current_record(s,"TERMINAL");if(!terminal)return 0;free(terminal);
    char *original=ffr3_current_record(s,"ORIGINAL"),*original_blob=original?ffr3_blob_ref("original-record",original):NULL;
    if(original_blob){char hash[65],name[80];
        if(!ffr3_json_string_value(original_blob,"hash",hash,sizeof(hash))){free(original);free(original_blob);return 0;}
        snprintf(name,sizeof(name),"%s.blob",hash);
        if(!ffr3_publish_immutable(s->prepared->blobs,name,original,strlen(original),&s->prepared->stop)){free(original);free(original_blob);return 0;}
    }
    if(!original_blob){free(original);return 0;}
    unsigned long long closed=0;char *closure=ffr3_original_closure(s,&closed);if(!closure)return 0;
    char *predecessor=ffr3_json_field(s->prepared->lineage,"predecessor"),*termination=NULL;
    while(predecessor&&ffr3_budget(&s->prepared->stop)){termination=ffr3_find_proof(s,"EXECUTOR_TERMINATION",NULL,predecessor);if(termination)break;struct timespec pause={0,1000000};nanosleep(&pause,NULL);}
    char *original_payload=original?ffr3_json_field(original,"payload"):NULL,*reservation=original_payload?ffr3_json_field(original_payload,"reservation"):NULL;
    /* The original record names Evidence; ORIGINAL_CONTROLLER names its exact
     * three-field Blob, with no new copy or reconstructed approval. */
    char *reservation_blob=NULL;
    if(reservation){char identity[256],hash[65],bytes[32];if(ffr3_json_string_value(reservation,"identity",identity,sizeof(identity))&&ffr3_json_string_value(reservation,"hash",hash,sizeof(hash))&&ffr3_json_string_value(reservation,"bytes",bytes,sizeof(bytes)))reservation_blob=ffr3_format("{\"bytes\":\"%s\",\"hash\":\"%s\",\"identity\":\"%s\"}",bytes,hash,identity);}
    char *executor=termination?ffr3_proof_blob(termination):NULL,*closure_ref=ffr3_proof_blob(closure),*admissions=ffr3_array_refs(s->admissions,s->count),*dispatches=ffr3_array_refs(s->dispatches,s->count);
    char *payload=original_blob&&reservation_blob&&executor&&closure_ref&&admissions&&dispatches?ffr3_format("{\"admission_ledger\":%s,\"child_right\":\"CLOSED_UNUSED\",\"consumption_right\":\"CLOSED_UNUSED\",\"control_capability\":%s,\"controller\":%s,\"dispatch_ledger\":%s,\"execution_closure\":%s,\"executor\":%s,\"identity\":\"native-original-controller\",\"lineage\":%s,\"original\":%s,\"reservation\":%s,\"sealed_ns\":\"%llu\",\"state\":\"TERMINAL_BEFORE_CHILD\"}",admissions,s->capability_ref,s->prepared->controller,dispatches,closure_ref,executor,s->prepared->lineage,original_blob,reservation_blob,closed):NULL;
    char *raw=payload?ffr3_signed_publish(s->prepared,&s->codec,"ORIGINAL_CONTROLLER",1,payload,ffr3_now_ns()):NULL;int valid=raw!=NULL;
    free(closure);free(predecessor);free(termination);free(original);free(original_blob);free(original_payload);free(reservation);free(reservation_blob);free(executor);free(closure_ref);free(admissions);free(dispatches);free(payload);free(raw);return valid;
}
static int ffr3_read_original_response(int fd,char *response,size_t capacity,const struct timespec *stop) {
    /* The counted P handler flushes its 202 before waiting for C's closure.
     * EOF therefore cannot be the response boundary. This R3-only reader
     * accepts one exact bounded Content-Length frame under the same stop. */
    size_t used=0,total=0;int framed=0;
    if(!response||capacity<32)return -1;
    while(ffr3_budget(stop)){
        if(framed&&used==total)return (int)used;
        if(used>=capacity-1||!recovery_wait_io(fd,POLLIN,stop))return -1;
        size_t remaining=framed?total-used:capacity-1-used;
        ssize_t count=read(fd,response+used,remaining);
        if(count<0&&(errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK))continue;
        if(count<=0||memchr(response+used,0,(size_t)count))return -1;
        used+=(size_t)count;response[used]=0;
        if(!framed){
            char *end=strstr(response,"\r\n\r\n");if(!end)continue;
            char *line=strstr(response,"\r\n");
            if(!line||line-response<12||strncmp(response,"HTTP/1.0 ",9)||
               strspn(response+9,"0123456789")!=3||response[12]!=' ')return -1;
            for(char *p=response;p<line;p++)if((unsigned char)*p<32||(unsigned char)*p>126)return -1;
            size_t length=0;int lengths=0;
            for(char *cursor=line+2;cursor<end;){
                char *next=strstr(cursor,"\r\n"),*colon=memchr(cursor,':',next?(size_t)(next-cursor):0);
                if(!next||next>end||!colon||colon==cursor||colon+1>=next||colon[1]!=' ')return -1;
                for(char *p=cursor;p<colon;p++)if(!((*p>='A'&&*p<='Z')||(*p>='a'&&*p<='z')||(*p>='0'&&*p<='9')||*p=='-'))return -1;
                for(char *p=colon+2;p<next;p++)if((unsigned char)*p<32||(unsigned char)*p>126)return -1;
                size_t name=(size_t)(colon-cursor);
                if(name==17&&!strncasecmp(cursor,"Transfer-Encoding",name))return -1;
                if(name==14&&!strncasecmp(cursor,"Content-Length",name)){
                    if(++lengths!=1||colon+2==next)return -1;
                    for(char *p=colon+2;p<next;p++){
                        if(*p<'0'||*p>'9'||length>(capacity-(size_t)(*p-'0'))/10)return -1;
                        length=length*10+(size_t)(*p-'0');
                    }
                    if(next-(colon+2)>1&&colon[2]=='0')return -1;
                }
                cursor=next+2;
            }
            size_t header=(size_t)(end-response)+4;
            if(lengths!=1||length>capacity-1-header)return -1;
            total=header+length;framed=1;if(used>total)return -1;
        }
    }
    return -1;
}
static int ffr3_original_post(FFR3Session *s,const char *generation,const char *token) {
    const char *gate="ENDPOINT_UNAVAILABLE";
    char *predecessor=ffr3_json_field(s->prepared->lineage,"predecessor"),*endpoint=predecessor?ffr3_find_proof(s,"ENDPOINT_CONFIGURATION",NULL,predecessor):NULL;
    char *payload=endpoint?ffr3_json_field(endpoint,"payload"):NULL;char port[16],host[32];int valid=payload&&ffr3_json_string_value(payload,"port",port,sizeof(port))&&ffr3_json_string_value(payload,"host",host,sizeof(host))&&!strcmp(host,"127.0.0.1");
    unsigned long number=valid?strtoul(port,NULL,10):0;valid=valid&&number>=1&&number<=65535;
    int descriptor=valid?socket(AF_INET,SOCK_STREAM,0):-1;if(descriptor<0)valid=0;
    if(valid){valid=fcntl(descriptor,F_SETFD,FD_CLOEXEC)==0&&fcntl(descriptor,F_SETFL,O_NONBLOCK)==0;struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_port=htons((uint16_t)number);inet_pton(AF_INET,"127.0.0.1",&address.sin_addr);
        gate="CONNECT_UNAVAILABLE";
        int connected=valid?connect(descriptor,(struct sockaddr*)&address,sizeof(address)):-1;valid=valid&&(connected==0||errno==EINPROGRESS);
        if(valid&&connected!=0){valid=recovery_wait_io(descriptor,POLLOUT,&s->prepared->stop);int error=0;socklen_t size=sizeof(error);if(valid)valid=getsockopt(descriptor,SOL_SOCKET,SO_ERROR,&error,&size)==0&&!error;}}
    char *request=valid?ffr3_format("POST /control/shutdown HTTP/1.0\r\nHost: 127.0.0.1:%s\r\nX-Kronos-Backend-Pid: %ld\r\nX-Kronos-Restart-Token: %s\r\nX-Kronos-Maintenance-Generation: %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",port,(long)s->codec.predecessor,token,generation):NULL;
    if(valid){gate="REQUEST_UNAVAILABLE";valid=request&&ffr3_helper_write(descriptor,request,strlen(request),&s->prepared->stop);}
    if(request){memset(request,0,strlen(request));free(request);}char response[8192]={0};
    if(valid){gate="RESPONSE_UNVERIFIED";int length=ffr3_read_original_response(descriptor,response,sizeof(response),&s->prepared->stop);char *body=length>0?strstr(response,"\r\n\r\n"):NULL;valid=length>0&&!strncmp(response,"HTTP/1.0 202 ",13)&&body&&!strcmp(body+4,"{\"status\":\"DRAINING\"}");
        if(!valid&&length>=12&&!strncmp(response,"HTTP/1.",7)&&strspn(response+9,"0123456789")>=3)fprintf(stderr,"KRONOS_R3_ORIGINAL_HTTP_STATUS:%.3s\n",response+9);}
    if(!valid)fprintf(stderr,"KRONOS_R3_ORIGINAL_POST:%s\n",gate);
    if(descriptor>=0)close(descriptor);free(predecessor);free(endpoint);free(payload);return valid&&ffr3_budget(&s->prepared->stop);
}

static int ffr3_original_shutdown(FFR3Session *s) {
    char *authority=ffr3_original_prepare(s);if(!authority){fputs("KRONOS_R3_ORIGINAL_GATE:PREPARATION_INCOMPLETE\n",stderr);return 0;}free(authority);
    unsigned long long now=ffr3_now_ns();if(!ffr3_admission(s,"backend-maintenance-drain","DISPATCH_SHUTDOWN","[]",now)||!ffr3_dispatch(s,"NOT_DISPATCHED",NULL,"[]",0,0,1)||!ffr3_dispatch(s,"DISPATCHED",NULL,"[]",now,0,1)){fputs("KRONOS_R3_ORIGINAL_GATE:DISPATCH_INCOMPLETE\n",stderr);return 0;}
    char *generation_raw=ffr3_json_field(s->prepared->lineage,"generation");char generation[256];int valid=generation_raw&&ffr3_json_string_value(s->prepared->lineage,"generation",generation,sizeof(generation));free(generation_raw);
    char token[65]={0};long process=0;if(valid)valid=sscanf(s->control,"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%64[0-9a-f]",&process,token)==2&&valid_token(token);
    if(valid)valid=ffr3_original_post(s,generation,token);memset(token,0,sizeof(token));
    if(!ffr3_dispatch(s,valid?"COMPLETED":"FAILED_CLOSED",NULL,"[]",now,ffr3_now_ns(),valid))return 0;
    if(!valid){fputs("KRONOS_R3_ORIGINAL_GATE:SHUTDOWN_NOT_ACCEPTED\n",stderr);return 0;}
    valid=ffr3_close_original(s);if(!valid)fputs("KRONOS_R3_ORIGINAL_GATE:CLOSURE_INCOMPLETE\n",stderr);return valid;
}
static char *ffr3_original_preparation_assertion(const FFR3PreparedNative *p) {
    char *wanted=ffr3_json_field(p->record,"original_preparation");if(!wanted)return NULL;
    DIR *directory=ffr3_directory_stream(p->preparation);if(!directory){free(wanted);return NULL;}struct dirent *entry;char *result=NULL;size_t count=0;int valid=1;
    while((entry=readdir(directory))&&valid){const char *name=entry->d_name;if(strlen(name)!=68||strcmp(name+64,".pin"))continue;if(++count>4096){valid=0;break;}
        size_t bytes=0;char *pin=ffr3_capture_at(p->preparation,name,FFR3_MAX_RECORD,&bytes,1,&p->stop),*reference=pin?ffr3_json_field(pin,"preparation"):NULL;
        if(reference&&!strcmp(reference,wanted)){
            if(result){valid=0;free(pin);free(reference);break;}FFR3PreparedNative previous=*p;previous.pin=pin;
            previous.record=ffr3_blob_at(p->preparation_records,reference,"json",&p->stop);
            char *catalogue=pin?ffr3_json_field(pin,"catalogue"):NULL;previous.catalogue=catalogue?ffr3_blob_at(p->preparation_records,catalogue,"json",&p->stop):NULL;
            char approval_name[96];snprintf(approval_name,sizeof(approval_name),"%.*s.approval",64,name);previous.approval=ffr3_capture_at(p->preparation,approval_name,FFR3_MAX_RECORD,&bytes,1,&p->stop);
            previous.attempt=previous.record?ffr3_json_field(previous.record,"attempt"):NULL;previous.mode=strdup("\"ORIGINAL\"");
            if(previous.record&&previous.catalogue&&previous.approval&&previous.attempt&&previous.mode)result=ffr3_preparation_assertion(&previous);
            free(previous.record);free(previous.catalogue);free(previous.approval);free(previous.attempt);free(previous.mode);free(catalogue);
        }free(pin);free(reference);
    }
    closedir(directory);free(wanted);if(!valid){free(result);return NULL;}return result;
}
static int ffr3_ref_order(const void *left,const void *right) {
    char a[256],b[256];const char *x=*(const char *const*)left,*y=*(const char *const*)right;
    if(!ffr3_json_string_value(x,"identity",a,sizeof(a))||!ffr3_json_string_value(y,"identity",b,sizeof(b)))return strcmp(x,y);return strcmp(a,b);
}
static char *ffr3_fact_outputs(FFR3Session *s) {
    if(s->fact_count>4)return NULL;qsort(s->fact_refs,s->fact_count,sizeof(s->fact_refs[0]),ffr3_ref_order);
    FFR3Buffer out={0};int valid=ffr3_text(&out,"[");
    for(size_t i=0;valid&&i<s->fact_count;i++)valid=(!i||ffr3_text(&out,","))&&ffr3_text(&out,s->fact_refs[i]);
    if(valid)valid=ffr3_text(&out,"]");if(!valid){free(out.bytes);return NULL;}return out.bytes;
}
static int ffr3_execute_prepared(void) {
    FFR3PreparedNative prepared;if(!ffr3_native_stage(&prepared,1)){fputs("KRONOS_R3_CONTROL_GATE:PREPARATION_UNAVAILABLE\n",stderr);return 1;}
    FFR3Session session={0};session.prepared=&prepared;session.grant_writer=-1;
    const char *gate="CAPABILITY_UNVERIFIED";
    session.capability=ffr3_native_capability(&prepared,&session.codec);session.capability_ref=session.capability?ffr3_proof_blob(session.capability):NULL;
    int valid=session.capability&&session.capability_ref;unsigned long long origin=(unsigned long long)prepared.origin.tv_sec*1000000000ULL+(unsigned long long)prepared.origin.tv_nsec;
    if(valid&&!strcmp(prepared.mode,"\"ORIGINAL\"")){gate="ORIGINAL_ADMISSION_UNAVAILABLE";valid=ffr3_admission(&session,"original.authorize","AUTHORIZE","[]",origin)&&ffr3_dispatch(&session,"NOT_DISPATCHED",NULL,"[]",0,0,1)&&ffr3_dispatch(&session,"DISPATCHED",NULL,"[]",origin,0,1);}
    /* Raw checkpoint publication belongs to this already counted original
     * operation. A recovery controller may verify only existing custody. */
    if(valid){gate="CONTROL_UNVERIFIED";valid=ffr3_retain_control(&session);}
    struct passwd *account=getpwuid(geteuid());char repository[PATH_MAX],python[PATH_MAX];
    if(valid){gate="SOURCE_FRAME_UNAVAILABLE";valid=account&&discover_repository(account->pw_dir,repository)&&snprintf(python,sizeof(python),"%s/.venv/bin/python",repository)<(int)sizeof(python);}
    char entry[512]={0};char *frame=NULL,*context=NULL;size_t length=0;
    if(valid){frame=ffr3_build_pin_frame(&prepared,repository,entry,&length);context=frame?ffr3_session_context(&session,!strcmp(prepared.mode,"\"ORIGINAL\"")?"PREPARATION":"RECOVERY_CLAIM",entry):NULL;valid=frame&&context;if(valid){gate="HELPER_UNVERIFIED";valid=ffr3_run_broker(&session,python,frame,length,context);}}
    if(!strcmp(prepared.mode,"\"ORIGINAL\"")&&session.admission){
        char *outputs=ffr3_fact_outputs(&session);
        valid=outputs&&ffr3_dispatch(&session,valid?"COMPLETED":"FAILED_CLOSED",session.helper_process,outputs,origin,ffr3_now_ns(),valid)&&valid;free(outputs);
        if(valid){gate="ORIGINAL_TERMINATION_UNVERIFIED";valid=ffr3_original_shutdown(&session);}
    }
    free(frame);free(context);free(session.helper_process);for(size_t i=0;i<session.fact_count;i++)free(session.fact_refs[i]);free(session.capability);free(session.capability_ref);if(session.control){memset(session.control,0,session.control_bytes);free(session.control);}memset(&session.codec,0,sizeof(session.codec));
    if(!valid){unsigned long long now=ffr3_now_ns();fprintf(stderr,"KRONOS_R3_CONTROL_GATE:%s;elapsed_ns=%llu\n",gate,now>=origin?now-origin:0);}
    if(session.grant_writer>=0)close(session.grant_writer);ffr3_release_preparation(&prepared);
    return valid?0:1;
}

int main(void) {
    const char *mode = getenv("KRONOS_LAUNCH_MODE");
    /* Signed-package execution check: no filesystem, runtime, or Browser action. */
    if (mode != NULL && strcmp(mode, "PACKAGE_VERIFY") == 0) {
        puts("KRONOS_LAUNCHER_PACKAGE_V1_OK");
        return 0;
    }
    if (mode != NULL && strcmp(mode, "FAILED_FENCED_PREPARATION") == 0)
        return ffr3_execute_prepared();
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
            (!recovery_authority.swing_incident && !recovery_authority.swing_release && (snprintf(relation,sizeof(relation),"%s/Library/Application Support/KRONOS/evidence/intraday-v1/live-shadow-v1/epochs-v1/WO06H-SUCCESSOR_COMPATIBILITY-%s.json",home,
                recovery_authority.historical ? "1a9a7b8b997447716f1b6f11b02fbcccf88fda2644b4a2af23604dbf5f293976" :
                    "4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef")>=(int)sizeof(relation) ||
            strcmp(recovery_authority.relation,relation))) ||
            !recovery_package_identity(repository,python,canonical_bundle,installed) || strcmp(installed,recovery_authority.package) ||
            !recovery_package_identity(repository,python,recovery_authority.rollback,rollback) || strcmp(rollback,recovery_authority.rollback_identity) ||
            !recovery_assess(&recovery_authority,repository,python)) { memset(token,0,sizeof(token));return show_restart_blocked(); }
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
                !recovery_assess(&recovery_authority,repository,python) ||
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
        if(!recovery_time_valid(&recovery_authority,final_now)){
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
