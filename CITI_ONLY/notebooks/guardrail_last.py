"""
CITI Hub GuardRail wrapper (module name: guardrail_last).

Rebuilt from the Hub source shared in chat. Internal Hub modules (Config,
ServiceCoin, ServiceJwt, ServiceVault) exist only on CITI JupyterHub; locally
this file raises ImportError and the notebook falls back to the mock path.

Usage (notebook Cell 6):
    from guardrail_last import GuardRail
    GuardRail.INITIALIZE(soeId)
    _, completion = GuardRail.CHAT_COMPLETIONS_CREATE(model=..., messages=...)
"""

import inspect, os, random, re, socket, threading, time
# import logging
# import sys
from datetime import datetime, timedelta, timezone
from threading import local

from openai import OpenAI
from openai._legacy_response import LegacyAPIResponse
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.create_embedding_response import CreateEmbeddingResponse

from Config import Config
from ServiceCoin import ServiceCoin
from ServiceJwt import ServiceJwt
from ServiceVault import ServiceVault


class GuardRail:
    _THREAD_LOCAL: local = local()
    _initialization_lock = threading.Lock()
    _shared_open_ai_client: OpenAI = None
    _shared_token_refresh_at: datetime = None

    def _SET_CONFIG(config: Config) -> None:
        assert config != None
        GuardRail._THREAD_LOCAL.config = config

    def _GET_CONFIG() -> Config:
        return GuardRail._THREAD_LOCAL.config

    def _SET_OPEN_AI_CLIENT(openAIClient: OpenAI) -> None:
        assert openAIClient != None
        GuardRail._shared_open_ai_client = openAIClient

    def _GET_OPEN_AI_CLIENT() -> OpenAI:
        return GuardRail._shared_open_ai_client

    def _GET_REQUEST_AT() -> datetime:
        return GuardRail._THREAD_LOCAL.requestAt

    def _SET_REQUEST_AT() -> datetime:
        GuardRail._THREAD_LOCAL.requestAt = datetime.now(timezone.utc)
        return GuardRail._THREAD_LOCAL.requestAt

    def _GET_RESPONSE_AT() -> datetime:
        return GuardRail._THREAD_LOCAL.responseAt

    def _SET_RESPONSE_AT() -> datetime:
        GuardRail._THREAD_LOCAL.responseAt = datetime.now(timezone.utc)
        return GuardRail._THREAD_LOCAL.responseAt

    def _VALIDATE_SOE_ID(soeId: str) -> None:
        # Not shown in the Hub screenshots; minimal guard only (non-empty string).
        assert isinstance(soeId, str) and soeId.strip() != "", "soeId must be a non-empty string"

    def _SET_SOE_ID(soeId: str) -> None:
        GuardRail._VALIDATE_SOE_ID(soeId)
        GuardRail._THREAD_LOCAL.soeId = soeId

    def _GET_SOE_ID() -> str:
        return GuardRail._THREAD_LOCAL.soeId

    def _SET_TOKEN_REFRESH_AT(tokenRefreshAt: datetime) -> None:
        assert tokenRefreshAt != None
        GuardRail._shared_token_refresh_at = tokenRefreshAt

    def _GET_TOKEN_REFRESH_AT() -> datetime:
        return GuardRail._shared_token_refresh_at

    def INITIALIZE(soeId: str) -> None:
        GuardRail._SET_SOE_ID(soeId)
        config = Config('uat')
        GuardRail._SET_CONFIG(config)

        # log = logging.getLogger('httpx')
        # log.addHandler(logging.StreamHandler(sys.stdout))
        # log.setLevel(logging.DEBUG)

        os.environ['REQUESTS_CA_BUNDLE'] = 'certs/CitiInternalCAChain_PROD.pem'
        os.environ['SSL_CERT_FILE'] = 'certs/CitiInternalCAChain_PROD.pem'
        # print(f'{threading.current_thread().name}: Hostname: {socket.gethostname()}')
        # print(f'{threading.current_thread().name}: IP Address: {socket.gethostbyname(socket.gethostname())}')
        os.environ['OPENAI_API_KEY'] = ''
        GuardRail._INITIALIZE_OPEN_AI()

    def _INITIALIZE_OPEN_AI() -> None:
        with GuardRail._initialization_lock:
            # Check if initialization is needed
            now = datetime.now(timezone.utc)
            refresh_at = GuardRail._GET_TOKEN_REFRESH_AT()
            if GuardRail._GET_OPEN_AI_CLIENT() and refresh_at and now < refresh_at:
                return  # Already initialized and token is valid

            print(f"{threading.current_thread().name}: Initializing or refreshing OpenAI client...")
            config = GuardRail._GET_CONFIG()

            serviceVault = ServiceVault(config.pathCertCa(),
                                        config.namespaceVault(),
                                        config.urlVault())
            print(f'{threading.current_thread().name}: {serviceVault}')
            serviceCoin = ServiceCoin(config.pathCertCa(),
                                      config.urlCoin())
            print(f'{threading.current_thread().name}: {serviceCoin}')
            serviceJwt = ServiceJwt(config.pathCertCa(),
                                    config.urlCoin())
            print(f'{threading.current_thread().name}: {serviceJwt}')

            responseAuthAppRoleLogin = serviceVault.authAppRoleLogin(config.idAppRole(),
                                                                     config.idAppRoleSecret())
            # print(f'{threading.current_thread().name}: Client token: {responseAuthAppRoleLogin.auth.client_token}')
            # print(f'{threading.current_thread().name}: Role name: {responseAuthAppRoleLogin.auth.metadata.role_name}')

            service = 'service-genai-poc'
            responseGetCoinSecret = serviceVault.getCoinSecret(responseAuthAppRoleLogin.auth.client_token,
                                                               config.idCsi(),
                                                               config.nameComponent(),
                                                               service)
            # print(f'{threading.current_thread().name}: Service: {service}')
            # print(f'{threading.current_thread().name}: Client Id: {responseGetCoinSecret.data.data.client_id}')
            # print(f'{threading.current_thread().name}: Client secret: {responseGetCoinSecret.data.data.client_secret}')
            responseAsTokenOAuth2 = serviceCoin.asTokenOAuth2(responseGetCoinSecret.data.data.client_id,
                                                              responseGetCoinSecret.data.data.client_secret,
                                                              config.r2d2Scope(),
                                                              config.r2d2Permission())
            # print(f'{threading.current_thread().name}: Access token: {responseAsTokenOAuth2.access_token}')
            # print(f'{threading.current_thread().name}: Token type: {responseAsTokenOAuth2.token_type}')
            # print(f'{threading.current_thread().name}: Expires: {responseAsTokenOAuth2.expires_in}')
            keySet = serviceJwt.getPF3wks()
            jwtClaims = serviceJwt.validateClaims(responseAsTokenOAuth2.access_token,
                                                  keySet,
                                                  config.r2d2Scope(),
                                                  config.r2d2Permission())
            # print(f'{threading.current_thread().name}: jwtClaims: {jwtClaims}')
            exp = datetime.fromtimestamp(jwtClaims.exp, tz=timezone.utc)
            tokenRefreshAt = exp - timedelta(minutes=5)
            # now = datetime.now(timezone.utc)
            # print(f'{threading.current_thread().name}: jwtClaims.exp: {jwtClaims.exp}')
            # print(f'{threading.current_thread().name}: tokenRefreshAt: {tokenRefreshAt.strftime("%Y-%m-%d %H:%M:%S.%f")}')
            # print(f'{threading.current_thread().name}: now: {now.strftime("%Y-%m-%d %H:%M:%S.%f")}')

            headers = {'Authorization': f"Bearer {responseAsTokenOAuth2.access_token}"}
            openAIClient = OpenAI(
                base_url="https://r2d2-c1p0-icg-msst-genaihub-178909.apps.namicg3M02u.ecs.dyn.nsroot.net/stellar/v1",
                default_headers=headers
            )
            GuardRail._SET_TOKEN_REFRESH_AT(tokenRefreshAt)
            GuardRail._SET_OPEN_AI_CLIENT(openAIClient)

    def CHAT_COMPLETIONS_CREATE(*args, **kwargs) -> tuple[str, ChatCompletion]:
        while True:
            requestAt = GuardRail._SET_REQUEST_AT()
            if (requestAt > GuardRail._GET_TOKEN_REFRESH_AT()):
                GuardRail._INITIALIZE_OPEN_AI()
            openAIClient = GuardRail._GET_OPEN_AI_CLIENT()
            completionsClient = openAIClient.chat.completions.with_raw_response
            # print(f'{threading.current_thread().name}: {type(completionsClient)=}')
            rawResponse = completionsClient.create(*args, **kwargs)
            # print(f'{threading.current_thread().name}: {type(rawResponse)=}')
            # print(f'{threading.current_thread().name}: {rawResponse=}')
            statusCode = rawResponse.status_code
            # print(f'{threading.current_thread().name}: {type(statusCode)=}')
            # print(f'{threading.current_thread().name}: {statusCode=}')
            if statusCode == 429:
                sleepInterval = random.randint(1, 30)
                print(f'{threading.current_thread().name}: Sleeping for {sleepInterval} sec and then retrying.')
                time.sleep(sleepInterval)
                continue
            if statusCode == 200:
                headers = rawResponse.headers
                # print(f'{threading.current_thread().name}: {type(headers)=}')
                # print(f'{threading.current_thread().name}: {headers=}')
                r2d2RequestId = headers.get('x-r2d2-requestid', None)
                # print(f'{threading.current_thread().name}: {type(r2d2RequestId)=}')
                # print(f'{threading.current_thread().name}: {r2d2RequestId=}')
                completion = rawResponse.parse()
                # print(f'{threading.current_thread().name}: {type(completion)=}')
                # print(f'{threading.current_thread().name}: {completion=}')

                GuardRail._SET_RESPONSE_AT()
                requestAt = GuardRail._GET_REQUEST_AT()
                responseAt = GuardRail._GET_RESPONSE_AT()
                llmResponseTime = responseAt - requestAt
                if (llmResponseTime.total_seconds() > 15):
                    print(f'{threading.current_thread().name}: LLM Provider is slow! {r2d2RequestId=}, {llmResponseTime.total_seconds()=}')
                else:
                    print(f'{threading.current_thread().name}: LLM Provider is fast! {r2d2RequestId=}, {llmResponseTime.total_seconds()=}')
                return r2d2RequestId, completion
            raise Exception(f'{threading.current_thread().name}: Error: {statusCode=}, {rawResponse=}')

    def CHAT_COMPLETIONS_PARSE(*args, **kwargs) -> tuple[str, ChatCompletion]:
        while True:
            requestAt = GuardRail._SET_REQUEST_AT()
            if (requestAt > GuardRail._GET_TOKEN_REFRESH_AT()):
                GuardRail._INITIALIZE_OPEN_AI()
            openAIClient = GuardRail._GET_OPEN_AI_CLIENT()
            completionsClient = openAIClient.beta.chat.completions.with_raw_response
            # print(f'{threading.current_thread().name}: {type(completionsClient)=}')
            rawResponse = completionsClient.parse(*args, **kwargs)
            # print(f'{threading.current_thread().name}: {type(rawResponse)=}')
            # print(f'{threading.current_thread().name}: {rawResponse=}')
            statusCode = rawResponse.status_code
            # print(f'{threading.current_thread().name}: {type(statusCode)=}')
            # print(f'{threading.current_thread().name}: {statusCode=}')
            if statusCode == 429:
                sleepInterval = random.randint(1, 30)
                print(f'{threading.current_thread().name}: Sleeping for {sleepInterval} sec and then retrying.')
                time.sleep(sleepInterval)
                continue
            if statusCode == 200:
                headers = rawResponse.headers
                # print(f'{threading.current_thread().name}: {type(headers)=}')
                # print(f'{threading.current_thread().name}: {headers=}')
                r2d2RequestId = headers.get('x-r2d2-requestid', None)
                # print(f'{threading.current_thread().name}: {type(r2d2RequestId)=}')
                # print(f'{threading.current_thread().name}: {r2d2RequestId=}')
                completion = rawResponse.parse()
                # print(f'{threading.current_thread().name}: {type(completion)=}')
                # print(f'{threading.current_thread().name}: {completion=}')

                GuardRail._SET_RESPONSE_AT()
                requestAt = GuardRail._GET_REQUEST_AT()
                responseAt = GuardRail._GET_RESPONSE_AT()
                llmResponseTime = responseAt - requestAt
                if (llmResponseTime.total_seconds() > 15):
                    print(f'{threading.current_thread().name}: LLM Provider is slow! {r2d2RequestId=}, {llmResponseTime.total_seconds()=}')
                else:
                    print(f'{threading.current_thread().name}: LLM Provider is fast! {r2d2RequestId=}, {llmResponseTime.total_seconds()=}')
                return r2d2RequestId, completion
            raise Exception(f'{threading.current_thread().name}: Error: {statusCode=}, {rawResponse=}')

    def EMBEDDINGS_CREATE(*args, **kwargs) -> tuple[str, CreateEmbeddingResponse]:
        while True:
            requestAt = GuardRail._SET_REQUEST_AT()
            if (requestAt > GuardRail._GET_TOKEN_REFRESH_AT()):
                GuardRail._INITIALIZE_OPEN_AI()
            openAIClient = GuardRail._GET_OPEN_AI_CLIENT()
            embeddingsClient = openAIClient.embeddings.with_raw_response
            # print(f'{threading.current_thread().name}: {type(embeddingsClient)=}')
            rawResponse = embeddingsClient.create(*args, **kwargs)
            # print(f'{threading.current_thread().name}: {type(rawResponse)=}')
            # print(f'{threading.current_thread().name}: {rawResponse=}')
            statusCode = rawResponse.status_code
            # print(f'{threading.current_thread().name}: {type(statusCode)=}')
            # print(f'{threading.current_thread().name}: {statusCode=}')
            if statusCode == 429:
                sleepInterval = random.randint(1, 30)
                print(f'{threading.current_thread().name}: Sleeping for {sleepInterval} sec and then retrying.')
                time.sleep(sleepInterval)
                continue
            if statusCode == 200:
                headers = rawResponse.headers
                # print(f'{threading.current_thread().name}: {type(headers)=}')
                # print(f'{threading.current_thread().name}: {headers=}')
                r2d2RequestId = headers.get('x-r2d2-requestid', None)
                # print(f'{threading.current_thread().name}: {type(r2d2RequestId)=}')
                # print(f'{threading.current_thread().name}: {r2d2RequestId=}')
                embeddings = rawResponse.parse()
                # print(f'{threading.current_thread().name}: {type(embeddings)=}')
                # print(f'{threading.current_thread().name}: {embeddings=}')

                GuardRail._SET_RESPONSE_AT()
                requestAt = GuardRail._GET_REQUEST_AT()
                responseAt = GuardRail._GET_RESPONSE_AT()
                llmResponseTime = responseAt - requestAt
                if (llmResponseTime.total_seconds() > 15):
                    print(f'{threading.current_thread().name}: LLM Provider is slow! {r2d2RequestId=}, {llmResponseTime.total_seconds()=}')
                else:
                    print(f'{threading.current_thread().name}: LLM Provider is fast! {r2d2RequestId=}, {llmResponseTime.total_seconds()=}')
                return r2d2RequestId, embeddings
            raise Exception(f'{threading.current_thread().name}: Error: {statusCode=}, {rawResponse=}')
