from pyrit.prompt_target import HTTPTarget, get_http_target_regex_matching_callback_function


class HTTPTargetManager(HTTPTarget):
    def __init__(self, endpoint_url: str, regex_key: str, http_req: str):
        """
        Initialization method for the HTTPTargetManager class.
        :param endpoint_url: The target endpoint URL.
        :param regex_key: The regular expression pattern for extracting the necessary data from the response.
        :param http_req: Details of the HTTP request.
        """
        # Generate a parsing function.
        parsing_function = get_http_target_regex_matching_callback_function(key=regex_key, url=endpoint_url)

        # Call the parent class constructor
        super().__init__(
            http_request=http_req,
            callback_function=parsing_function
        )
