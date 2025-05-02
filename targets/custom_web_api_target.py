from pyrit.prompt_target import HTTPTarget, get_http_target_json_response_callback_function


class HTTPTargetManager(HTTPTarget):
    def __init__(self, raw_http_request: str, timeout: float = 300.0):
        """
        Initialization method for the HTTPTargetManager class.
        :param raw_http_request: Details of the HTTP request.
        """
        # Define callback function.
        parsing_fn = get_http_target_json_response_callback_function(key="response")

        # Call the parent class constructor
        super().__init__(
            http_request=raw_http_request,
            callback_function=parsing_fn,
            timeout=300.0
        )
