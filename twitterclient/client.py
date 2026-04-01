"""
TwitterClient — the main public API.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .http import TwitterHTTP
from .models import Timeline, Tweet, TwitterList, User
from .parser import (
    parse_conversation_tweet,
    parse_graph_user,
    parse_list,
    parse_search,
    parse_single_tweet,
    parse_timeline,
    parse_user_result,
)
from .sessions import SessionPool

# ── Endpoints ─────────────────────────────────────────────────────────────────
_EP_USER_BY_NAME        = "IGgvgiOx4QZndDHuD3x9TQ/UserByScreenName"
_EP_USER_BY_ID          = "VN33vKXrPT7p35DgNR27aw/UserResultByIdQuery"
_EP_USER_TWEETS         = "6QdSuZ5feXxOadEdXa4XZg/UserWithProfileTweetsQueryV2"
_EP_USER_TWEETS_REPLIES = "BDX77Xzqypdt11-mDfgdpQ/UserWithProfileTweetsAndRepliesQueryV2"
_EP_TWEET               = "b4pV7sWOe97RncwHcGESUA/ConversationTimeline"
_EP_TWEET_RESULT        = "sBoAB5nqJTOyR9sZ5qVLsw/TweetResultByRestId"
_EP_SEARCH              = "GcXk9vN_d1jUfHNqLacXQA/SearchTimeline"
_EP_LIST_TWEETS         = "VQf8_XQynI3WzH6xopOMMQ/ListTimeline"
_EP_LIST_BY_ID          = "cIUpT1UjuGgl_oWiY7Snhg/ListByRestId"

# ── Features — each endpoint uses its own subset ──────────────────────────────

_FEATURES_TWEET = json.dumps({
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}, separators=(",", ":"))

_FEATURES_TWEET_TOGGLES = json.dumps({
    "withArticleRichContentState": True,
    "withArticlePlainText": False,
    "withArticleSummaryText": True,
    "withArticleVoiceOver": True,
}, separators=(",", ":"))

_FEATURES_USER = json.dumps({
    "hidden_profile_subscriptions_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": True,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}, separators=(",", ":"))

_FEATURES_USER_TOGGLES = json.dumps({
    "withPayments": False,
    "withAuxiliaryUserLabels": True,
}, separators=(",", ":"))

_FEATURES_SEARCH = json.dumps({
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}, separators=(",", ":"))

# Features blob taken directly from a live browser request (April 2026)
_GQL_FEATURES = json.dumps({
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}, separators=(",", ":"))

_GQL_USER_FEATURES = json.dumps({
    "hidden_profile_subscriptions_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": True,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}, separators=(",", ":"))

_GQL_USER_FIELD_TOGGLES = json.dumps({
    "withPayments": False,
    "withAuxiliaryUserLabels": True,
}, separators=(",", ":"))


def _vars(**kwargs) -> str:
    return json.dumps({k: v for k, v in kwargs.items() if v is not None}, separators=(",", ":"))


class TwitterClient:
    def __init__(
        self,
        sessions_path: str | Path = "sessions.jsonl",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 15.0,
    ) -> None:
        self._pool = SessionPool(sessions_path)
        self._http = TwitterHTTP(
            self._pool,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout,
        )

    def _fetch(self, endpoint: str, variables: str, field_toggles: bool = False) -> dict:
        params = {
            "variables": variables,
            "features": _GQL_FEATURES,
        }
        if field_toggles:
            params["fieldToggles"] = _GQL_FIELD_TOGGLES
        return self._http.fetch(endpoint, params)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        js = self._fetch(_EP_USER_BY_ID, _vars(rest_id=user_id))
        return parse_user_result(js)

    def get_user(self, username: str) -> Optional[User]:
        username = username.lstrip("@")
        js = self._http.fetch(_EP_USER_BY_NAME, {
            "variables": _vars(screen_name=username, withGrokTranslatedBio=False),
            "features": _FEATURES_USER,
            "fieldToggles": _FEATURES_USER_TOGGLES,
        })
        return parse_user_result(js)

    def get_tweet(self, tweet_id: str) -> Optional[Tweet]:
        js = self._http.fetch(_EP_TWEET_RESULT, {
            "variables": _vars(
                tweetId=tweet_id,
                includePromotedContent=True,
                withBirdwatchNotes=True,
                withVoice=True,
                withCommunity=True,
            ),
            "features": _FEATURES_TWEET,
            "fieldToggles": _FEATURES_TWEET_TOGGLES,
        })
        return parse_single_tweet(js)

    def search(
        self,
        query: str,
        *,
        cursor: str = "",
        count: int = 20,
        product: str = "Latest",
    ) -> Timeline:
        js = self._http.fetch(_EP_SEARCH, {
            "variables": _vars(
                rawQuery=query,
                count=count,
                querySource="typed_query",
                product=product,
                withGrokTranslatedBio=False,
                **({} if not cursor else {"cursor": cursor}),
            ),
            "features": _FEATURES_SEARCH,
        })
        return parse_search(js, after=cursor)

    def get_timeline(
        self,
        username: str,
        *,
        cursor: str = "",
        count: int = 20,
        include_replies: bool = False,
    ) -> Timeline:
        username = username.lstrip("@")
        user = self.get_user(username)
        if not user:
            raise ValueError(f"User not found: @{username}")
        return self.get_timeline_by_id(
            user.id, cursor=cursor, count=count, include_replies=include_replies,
        )

    def get_timeline_by_id(
        self,
        user_id: str,
        *,
        cursor: str = "",
        count: int = 20,
        include_replies: bool = False,
    ) -> Timeline:
        endpoint = _EP_USER_TWEETS_REPLIES if include_replies else _EP_USER_TWEETS
        variables = _vars(rest_id=user_id, count=count)
        if cursor:
            variables = variables.replace("{", '{"cursor":"' + cursor + '",', 1)
        js = self._fetch(endpoint, variables)
        return parse_timeline(js, after=cursor)

    def get_list(self, list_id: str) -> Optional[TwitterList]:
        js = self._fetch(_EP_LIST_BY_ID, _vars(listId=list_id))
        return parse_list(js)

    def get_list_timeline(
        self,
        list_id: str,
        *,
        cursor: str = "",
        count: int = 20,
    ) -> Timeline:
        variables = _vars(
            listId=list_id,
            count=count,
            **({} if not cursor else {"cursor": cursor}),
        )
        js = self._fetch(_EP_LIST_TWEETS, variables)
        return parse_timeline(js, after=cursor)

    def iter_timeline(self, username: str, *, max_tweets: int = 100, include_replies: bool = False):
        cursor = ""
        collected = 0
        while collected < max_tweets:
            tl = self.get_timeline(username, cursor=cursor, include_replies=include_replies)
            if not tl.tweets:
                break
            for tweet in tl.tweets:
                if collected >= max_tweets:
                    return
                yield tweet
                collected += 1
            if not tl.next_cursor:
                break
            cursor = tl.next_cursor

    def iter_search(self, query: str, *, max_tweets: int = 100, product: str = "Latest"):
        cursor = ""
        collected = 0
        while collected < max_tweets:
            tl = self.search(query, cursor=cursor, product=product)
            if not tl.tweets:
                break
            for tweet in tl.tweets:
                if collected >= max_tweets:
                    return
                yield tweet
                collected += 1
            if not tl.next_cursor:
                break
            cursor = tl.next_cursor

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TwitterClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()