"""
@author: moloch

This is a Burp plugin to parse Content-Security-Policy headers and detect
possibly weaknesses and bypasses in the policy.
"""
# pylint: disable=E0602,C0103,W0621


from burp import IBurpExtender
from burp import IScannerCheck

from httplib import HTTPResponse
from StringIO import StringIO


class HttpDummySocket(object):

    """ A dummy socket object so we can use httplib to parse the bytearray """

    def __init__(self, byteResponse):
        self._file = StringIO(byteResponse)

    def makefile(self, *args, **kwargs):
        return self._file


class ContentSecurityPolicyScan(IScannerCheck):

    """ Implements the actual passive scan """

    CSP_HEADERS = ["content-security-policy",
                   "x-content-security-policy",
                   "x-webkit-csp"]

    def __init__(self, callbacks):
        """ Initialize instance variables """
        self.issues = []
        self._helpers = callbacks.getHelpers()
        self._burpHttpReqResp = None
        self.response = None

    def _getUrl(self):
        return self._helpers.analyzeRequest(self._burpHttpReqResp).getUrl()

    def _getHttpService(self):
        return self._burpHttpReqResp.getHttpService()

    def doPassiveScan(self, httpMessage):
        """
        This is a callback method for Burp, its called for each HTTP req/resp.
        Returns a list of IScanIssue(s)
        """
        if len(httpMessage.getResponse()):
            self._burpHttpReqResp = httpMessage
            self.proccessHttpResponse(httpMessage.getResponse())
        return self.issues

    def consolidateDuplicateIssues(self, existingIssue, newIssue):
        """
        This is a callback method for Burp, and is used to cleanup duplicate
        findings.
        @return An indication of which issue(s) should be reported in the main
        Scanner results. The method should return <code>-1</code> to report the
        existing issue only, <code>0</code> to report both issues, and
        <code>1</code> to report the new issue only.
        """
        if existingIssue.getIssueName() == newIssue.getIssueName() and existingIssue.getUrl() == newIssue.getUrl():
            return -1
        else:
            return 0

    def proccessHttpResponse(self, byteResponse):
        """ Processes only the HTTP repsonses with a CSP header """
        httpSocket = HttpDummySocket(bytearray(byteResponse))
        self.response = HTTPResponse(httpSocket)
        self.response.begin()
        for header in self.response.getheaders():
            if header[0].lower() in self.CSP_HEADERS:
                self.parseContentSecurityPolicy(header)

    def parseContentSecurityPolicy(self, cspHeader):
        """ Parses the CSP response header and searches for issues """
        csp = ContentSecurityPolicy(cspHeader[0], cspHeader[1])
        self.deprecatedHeaderCheck(csp)
        self.unsafeContentSourceCheck(csp)
        self.wildcardContentSourceCheck(csp)
        self.insecureContentSourceCheck(csp)
        self.missingDirectiveCheck(csp)

    def deprecatedHeaderCheck(self, csp):
        """
        Checks for the use of a deprecated header such as `X-WebKit-CSP'
        """
        if csp.is_deprecated_header():
            deprecatedHeader = DeprecatedHeader(
                httpService=self._getHttpService(),
                url=self._getUrl(),
                httpMessages=self._burpHttpReqResp,
                severity="Medium",
                confidence="Certain")
            self.issues.append(deprecatedHeader)

    def unsafeContentSourceCheck(self, csp):
        """ Checks the current CSP header for unsafe content sources """
        for directive in [SCRIPT_SRC, STYLE_SRC]:
            if UNSAFE_EVAL in csp[directive] or UNSAFE_INLINE in csp[directive]:
                unsafeContent = UnsafeContentSource(
                    httpService=self._getHttpService(),
                    url=self._getUrl(),
                    httpMessages=self._burpHttpReqResp,
                    severity="High",
                    confidence="Certain",
                    directive=directive)
                self.issues.append(unsafeContent)

    def wildcardContentSourceCheck(self, csp):
        """ Check content sources for wildcards '*' """
        for directive, contentSoruces in csp.iteritems():
            if contentSoruces is None:
                continue  # Skip unspecified directives in NO_FALLBACK
            if any("*" in src for src in contentSoruces):
                wildcardContent = WildcardContentSource(
                    httpService=self._getHttpService(),
                    url=self._getUrl(),
                    httpMessages=self._burpHttpReqResp,
                    severity="Medium",
                    confidence="Certain",
                    directive=directive)
                self.issues.append(wildcardContent)

    def insecureContentSourceCheck(self, csp):
        """ Check content sources for insecure `http:' sources """
        pass

    def missingDirectiveCheck(self, csp):
        """
        Check for missing directives that do not inherit from `default-src'
        """
        for directive in ContentSecurityPolicy.NO_FALLBACK:
            if directive not in csp:
                missingDirective = MissingDirective(
                    httpService=self._getHttpService(),
                    url=self._getUrl(),
                    httpMessages=self._burpHttpReqResp,
                    severity="Medium",
                    confidence="Certain",
                    directive=directive)
                self.issues.append(missingDirective)


class BurpExtender(IBurpExtender):

    """ Burp extension object """

    NAME = "CSP Bypass"

    def	registerExtenderCallbacks(self, callbacks):
        """ Entrypoint and setup """
        callbacks.setExtensionName(self.NAME)
        callbacks.registerScannerCheck(ContentSecurityPolicyScan(callbacks))

    def extensionUnloaded(self):
        """ Cleanup when the extension is unloaded """
        print "CSP Bypass extension was unloaded"