# No shebang line, this module is meant to be imported
#
# Copyright 2014 Oliver Palmer
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import re
from collections import namedtuple

try:
    from httplib import responses, OK
except ImportError:  # pragma: no cover
    from http.client import responses, OK


import treq
from twisted.internet.defer import Deferred
from twisted.internet.error import DNSLookupError
from twisted.internet.protocol import Protocol, connectionDone
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import Response as TWResponse, Headers, ResponseDone
from pyfarm.core.enums import STRING_TYPES

from pyfarm.agent.testutil import TestCase, BaseRequestTestCase
from pyfarm.agent.config import config
from pyfarm.agent.http.core.client import (
    Request, Response, request, head, get, post, put, patch, delete,
    get_direct, post_direct, delete_direct, put_direct, build_url,
    http_retry_delay, USERAGENT)


# fake object we use for triggering Response.connectionLost
responseDone = namedtuple("reason", ["type"])(type=ResponseDone)


class TestPartials(TestCase):
    def test_head(self):
        self.assertIs(head.func, request)
        self.assertEqual(head.args, ("HEAD", ))

    def test_get(self):
        self.assertIs(get.func, request)
        self.assertEqual(get.args, ("GET", ))

    def test_post(self):
        self.assertIs(post.func, request)
        self.assertEqual(post.args, ("POST", ))

    def test_put(self):
        self.assertIs(put.func, request)
        self.assertEqual(put.args, ("PUT", ))

    def test_patch(self):
        self.assertIs(patch.func, request)
        self.assertEqual(patch.args, ("PATCH", ))

    def test_delete(self):
        self.assertIs(delete.func, request)
        self.assertEqual(delete.args, ("DELETE", ))


class TestRequestErrors(BaseRequestTestCase):
    def test_invalid_empty_path(self):
        with self.assertRaisesRegexp(
                NotImplementedError, re.compile("No path.*")):
            request("GET", "http://localhost")

    def test_invalid_empty_hostname(self):
        with self.assertRaisesRegexp(
                NotImplementedError, re.compile("No hostname.*")):
            request("GET", "http://")

    def test_invalid_callback_type(self):
        with self.assertRaises(AssertionError):
            request("GET", "http://localhost/", callback="")

    def test_invalid_errback_type(self):
        with self.assertRaises(AssertionError):
            request("GET", "http://localhost/", errback="")

    def test_invalid_header_value_type(self):
        with self.assertRaises(NotImplementedError):
            request("GET", "/",
                    callback=lambda: None,
                    headers={"foo": None})

    def test_unknown_hostname(self):
        return get(self.HTTP_SCHEME + "://%s/" % os.urandom(8).encode("hex"),
                   callback=lambda _: self.fail("Unexpected success"),
                   errback=lambda failure:
                   self.assertIs(failure.type, DNSLookupError))


class RequestTestCase(BaseRequestTestCase):
    def setUp(self):
        super(RequestTestCase, self).setUp()
        config["agent_http_persistent_connections"] = False

    def get_url(self, url):
        assert isinstance(url, STRING_TYPES)
        return self.TEST_URL + ("/%s" % url if not url.startswith("/") else url)

    def get(self, url, **kwargs):
        return get(self.get_url(url), **kwargs)

    def post(self, url, **kwargs):
        return post(self.get_url(url), **kwargs)

    def put(self, url, **kwargs):
        return put(self.get_url(url), **kwargs)

    def delete(self, url, **kwargs):
        return delete(self.get_url(url), **kwargs)

    def assert_response(self, response, code,
                        content_type=None, user_agent=None):
        if content_type is None:
            content_type = "application/json"

        if user_agent is None:
            user_agent = ["PyFarm/1.0 (agent)"]

        # check some of the attribute we expect
        # against data coming back from the server
        try:
            data = response.json()
            if "headers" in data:
                self.assertEqual(data["headers"]["User-Agent"], user_agent[0])

            # even if we're making a https request the underlying
            # url might be http
            if "url" in data:
                self.assertIn(data["url"], (
                    response.request.url,
                    response.request.url.replace("https", "http")))
        except ValueError:
            pass

        # check the types under the hod
        self.assertIsInstance(response, Response)
        self.assertIsInstance(response.request, Request)
        self.assertIsInstance(response.headers, dict)

        # return code check
        self.assertIn(code, responses)
        self.assertEqual(response.code, code)
        self.assertEqual(response.code, response.response.code)

        # ensure our request and response attributes match headers match
        self.assertEqual(response.headers["Content-Type"], content_type)
        if "headers" in response.request.kwargs:
            self.assertEqual(
                response.request.kwargs["headers"]["User-Agent"], user_agent)
        self.assertEqual(response.content_type, content_type)


class DirectRequestTestCase(RequestTestCase):
    def get(self, url, **kwargs):
        return get_direct(self.get_url(url), **kwargs)

    def post(self, url, **kwargs):
        return post_direct(self.get_url(url), **kwargs)

    def put(self, url, **kwargs):
        return put_direct(self.get_url(url), **kwargs)

    def delete(self, url, **kwargs):
        return delete_direct(self.get_url(url), **kwargs)


class TestRetryDelay(TestCase):
    def test_config_defaults(self):
        config["agent_http_retry_delay_factor"] = 0
        config["agent_http_retry_delay_offset"] = 0
        self.assertEqual(http_retry_delay(), 0)
        config["agent_http_retry_delay_factor"] = 0
        config["agent_http_retry_delay_offset"] = 1
        self.assertEqual(http_retry_delay(), 1)

    def test_custom_offset_and_factor(self):
        self.assertEqual(
            http_retry_delay(offset=1, factor=1, rand=lambda: 1), 2)

    def test_invalid_type_offset(self):
        with self.assertRaises(AssertionError):
            http_retry_delay(offset="")

    def test_invalid_type_factor(self):
        with self.assertRaises(AssertionError):
            http_retry_delay(factor="")


class TestClientFunctions(RequestTestCase):
    def test_auth(self):
        username = os.urandom(6).encode("hex")
        password = os.urandom(6).encode("hex")

        def callback(response):
            self.assert_response(response, OK)
            self.assertEqual(
                response.json(),
                {"authenticated": True, "user": username})

        d = self.get(
            "/basic-auth/%s/%s" % (username, password),
            callback=callback, auth=(username, password),)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_redirect(self):
        def callback(response):
            self.assert_response(response, OK, content_type="text/html")
            self.assertIn("<title>Example Domain</title>", response.data())

        d = self.get(
            "/redirect-to?url=%s" % self.REDIRECT_TARGET,
            callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_gzipped(self):
        def callback(response):
            self.assert_response(response, OK)
            self.assertTrue(response.json()["gzipped"])

        d = self.get("/gzip", callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_retry(self):
        self.retried = False

        def callback(response):
            self.assert_response(response, OK)

            if not self.retried:
                retry = response.request.retry()
                self.assertIsInstance(retry, Deferred)
                self.retried = True
                return retry
            else:
                self.assertEqual(response.request.url, self.get_url("/get"))
                self.assertEqual(response.request.method, "GET")

        # special cleanup step to test self.retried
        self.addCleanup(lambda: self.assertTrue(self.retried, "not retried"))

        d = self.get("/get", callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d


class TestDirectMethods(DirectRequestTestCase):
    @inlineCallbacks
    def test_get(self):
        response = yield self.get("/get")
        self.assertEqual(response.code, OK)
        data = yield treq.json_content(response)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["headers"]["Content-Type"], "application/json")

    @inlineCallbacks
    def test_post(self):
        post_data = {"name": os.urandom(6).encode("hex")}
        response = yield self.post("/post", data=post_data)
        self.assertEqual(response.code, OK)
        data = yield treq.json_content(response)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["headers"]["User-Agent"], USERAGENT)
        self.assertEqual(data["json"], post_data)

    @inlineCallbacks
    def test_put(self):
        put_data = {"name": os.urandom(6).encode("hex")}
        response = yield self.put("/put", data=put_data)
        self.assertEqual(response.code, OK)
        data = yield treq.json_content(response)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["headers"]["User-Agent"], USERAGENT)
        self.assertEqual(data["json"], put_data)

    @inlineCallbacks
    def test_delete(self):
        response = yield self.delete("/delete")
        self.assertEqual(response.code, OK)
        data = yield treq.json_content(response)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["headers"]["User-Agent"], USERAGENT)
        self.assertIsNone(data["json"])


class TestMethods(RequestTestCase):
    def test_get(self):
        def callback(response):
            self.assert_response(response, OK)

        d = self.get("/get", callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_response_header(self):
        key = os.urandom(6).encode("hex")
        value = os.urandom(6).encode("hex")

        def callback(response):
            self.assertEqual(
                response.response.headers.getRawHeaders(key), [value])

        d = self.get(
            "/response-headers?%s=%s" % (key, value), callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_request_header(self):
        key = "X-" + os.urandom(6).encode("hex")
        value = os.urandom(6).encode("hex")

        def callback(response):
            data = response.json()
            self.assert_response(response, OK)
            self.assertEqual(response.request.kwargs["headers"][key], [value])

            # case insensitive comparison
            for k, v in data["headers"].items():
                if k.lower() == key.lower():
                    self.assertEqual(v, value)
                    break

        d = self.get("/get", callback=callback, headers={key: value})
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_url_argument(self):
        key = "X-" + os.urandom(6).encode("hex")
        value = os.urandom(6).encode("hex")

        def callback(response):
            data = response.json()
            self.assert_response(response, OK)
            self.assertEqual(data["args"], {key: value})

        d = self.get("/get?%s=%s" % (key, value), callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_post(self):
        key = os.urandom(6).encode("hex")
        value = os.urandom(6).encode("hex")

        def callback(response):
            self.assertEqual(response.json()["json"], {key: value})
            self.assert_response(response, OK)

        d = self.post("/post", callback=callback, data={key: value})
        d.addBoth(lambda r: self.assertIsNone(r))
        return d

    def test_delete(self):
        def callback(response):
            self.assert_response(response, OK)

        d = self.delete("/delete", callback=callback)
        d.addBoth(lambda r: self.assertIsNone(r))
        return d


class TestResponse(RequestTestCase):
    def setUp(self):
        super(TestResponse, self).setUp()
        self.callbacks = set()

    def test_instance_type(self):
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        r = Response(deferred, twisted_response, request)
        self.assertIsInstance(r, Protocol)

    def test_attributes(self):
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        r = Response(deferred, twisted_response, request)
        self.assertIs(r._deferred, deferred)
        self.assertIs(r.request, request)
        self.assertIs(r.response, twisted_response)
        self.assertEqual(r.method, request.method)
        self.assertEqual(r.url, request.url)
        self.assertEqual(r.code, twisted_response.code)
        self.assertEqual(r.content_type, "application/json")

    def test_headers(self):
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})
        r = Response(deferred, twisted_response, request)
        self.assertEqual(r.headers, {"Content-Type": "application/json"})
        self.assertEqual(r.request.kwargs["headers"],
                         {"Content-Type": "application/json"})

    def test_data_received(self):
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)

        r = Response(deferred, twisted_response, request)
        self.assertEqual(r._body, "")
        data = os.urandom(6).encode("hex")
        r.dataReceived(data)
        self.assertEqual(r._body, data)

    def test_response_done(self):
        deferred = Deferred()
        deferred.addCallback(lambda _: self.callbacks.add("success"))
        deferred.addErrback(lambda _: self.callbacks.add("failure"))
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        r = Response(deferred, twisted_response, request)
        r.connectionLost(responseDone)
        self.assertEqual(self.callbacks, set(["success"]))
        self.assertTrue(r._done)
        return deferred

    def test_connection_done(self):
        deferred = Deferred()
        deferred.addCallback(lambda _: self.callbacks.add("success"))
        deferred.addErrback(lambda _: self.callbacks.add("failure"))
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        r = Response(deferred, twisted_response, request)
        r.connectionLost(connectionDone)
        self.assertEqual(self.callbacks, set(["failure"]))
        self.assertFalse(r._done)
        return deferred

    def test_data_early(self):
        deferred = Deferred()
        deferred.addCallback(lambda _: self.callbacks.add("success"))
        deferred.addErrback(lambda _: self.callbacks.add("failure"))
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        r = Response(deferred, twisted_response, request)

        with self.assertRaises(RuntimeError):
            r.data()

    def test_data(self):
        deferred = Deferred()
        deferred.addCallback(lambda _: self.callbacks.add("success"))
        deferred.addErrback(lambda _: self.callbacks.add("failure"))

        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})
        data1 = os.urandom(6).encode("hex")
        data2 = os.urandom(6).encode("hex")
        data = data1 + data2
        r = Response(deferred, twisted_response, request)
        r.dataReceived(data1)
        r.dataReceived(data2)
        r.connectionLost(responseDone)
        self.assertEqual(self.callbacks, set(["success"]))
        self.assertTrue(r._done)
        self.assertEqual(r.data(), data)
        return deferred

    def test_json_early(self):
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        r = Response(deferred, twisted_response, request)

        with self.assertRaises(RuntimeError):
            r.json()

    def test_json_wrong_content_type(self):
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["text/html"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "text/html"}, "data": None})

        r = Response(deferred, twisted_response, request)
        r._done = True

        with self.assertRaisesRegexp(
                ValueError, re.compile("Not an application/json response\.")):
            r.json()

    def test_json_decoding_error(self):
        deferred = Deferred()
        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})
        r = Response(deferred, twisted_response, request)
        r._done = True
        with self.assertRaisesRegexp(ValueError,
                                     re.compile(
                                         "No JSON object could be decoded")):
            r.json()

    def test_json(self):
        deferred = Deferred()
        deferred.addCallback(lambda _: self.callbacks.add("success"))
        deferred.addErrback(lambda _: self.callbacks.add("failure"))

        twisted_headers = Headers({"Content-Type": ["application/json"]})
        twisted_response = TWResponse(
            ("HTTP", 1, 1), 200, "OK", twisted_headers, None)
        request = Request(
            method="GET", url="/",
            kwargs={
                "headers": {
                    "Content-Type": "application/json"}, "data": None})

        data = {
            os.urandom(6).encode("hex"): os.urandom(6).encode("hex"),
            os.urandom(6).encode("hex"): os.urandom(6).encode("hex")
        }

        r = Response(deferred, twisted_response, request)
        map(r.dataReceived, json.dumps(data))
        r.connectionLost(responseDone)
        self.assertEqual(self.callbacks, set(["success"]))
        self.assertTrue(r._done)
        self.assertEqual(r.json(), data)
        return deferred


class TestBuildUrl(TestCase):
    def test_basic_url(self):
        self.assertEqual(build_url("/foobar"), "/foobar")

    def test_url_with_arguments(self):
        self.assertEqual(
            build_url("/foobar", {"first": "foo", "second": "bar"}),
            "/foobar?first=foo&second=bar")

    def test_quoted_url(self):
        self.assertEqual(
            build_url("/foobar",
                      {"first": "foo", "second": "bar"}),
            "/foobar?first=foo&second=bar")

    def test_large_random_parameters(self):
        params = {}
        for i in range(50):
            params[os.urandom(24).encode("hex")] = os.urandom(24).encode("hex")

        expected = "/foobar?" + "&".join([
            "%s=%s" % (key, value)for key, value in sorted(params.items())])

        self.assertEqual(
            build_url("/foobar", params), expected)
