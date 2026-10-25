"""Fictional platform conversations. No platform APIs or external identifiers."""
from collections import Counter
from datetime import datetime, timezone
import random

from .world import NS, community, iso, ref


def metadata(doc):
    return doc['extensions'][NS]


def populate(builder, people, by_community):
    c, kb = builder.config, builder.kb['social']
    if c.social_platform == 'off':
        return
    rng = random.Random(f'{c.seed}:social-v2')
    platforms = kb['platforms'] if c.social_platform == 'mixed' else [c.social_platform]
    profile = kb['activity'][c.activity]
    groups, sessions, posts = {}, [], []
    days = list(range((builder.end-builder.start)//86400))
    weights = [profile['weekend_weight'] if datetime.fromtimestamp(builder.start+d*86400, timezone.utc).weekday() >= 5 else 1 for d in days]

    def scheduled(anchors):
        day = rng.choice(anchors) if anchors else rng.choices(days, weights=weights)[0]
        at = builder.start+day*86400+rng.choice(profile['hours'])*3600+rng.randrange(3600)
        return min(at, builder.end-7200)

    for platform in platforms:
        for j, members in enumerate(by_community):
            key = f'{platform}-{j}'
            group = builder.add('org', f'social-group-{key}', j, name=f'Fictional {platform} community {j+1}', organizationType='online-community')
            metadata(group).update(socialKind='group', platform=platform)
            channels = []
            for definition in kb['channels']:
                channel = builder.add('org', f'channel-{key}-{definition["name"]}', j, name=definition['name'], organizationType='online-channel', parentOrg=ref(group))
                metadata(channel).update(socialKind='channel', platform=platform, groupId=group['id'], topic=definition['topic'], writeRoles=definition['write_roles'])
                channels.append(channel)
            accounts = []
            for ordinal, i in enumerate(members):
                role = 'moderator' if ordinal == 0 else 'member'
                account = builder.add('user', f'social-account-{platform}-{i}', j, username=f'synthetic-{platform}-{i+1}', platform=platform,
                                      platformUserId=f'synthetic:{platform}:user:{i+1}', url=f'https://{platform}.example.invalid/users/{i+1}')
                metadata(account).update(socialKind='account', groupId=group['id'], channelIds=[d['id'] for d in channels], role=role, joinedAt=builder.start)
                people[i]['accounts'].append(ref(account))
                builder.edge(people[i], account, 'owns_account')
                membership = builder.edge(account, group, 'member_of_community')
                metadata(membership).update(role=role, joinedAt=builder.start)
                for channel in channels:
                    membership = builder.edge(account, channel, 'member_of_channel')
                    metadata(membership).update(role=role, joinedAt=builder.start)
                accounts.append(account)
            groups[key] = (group, channels, accounts)
            anchors = rng.sample(days, min(len(days), profile['burst_days'])) if profile['burst_days'] else []
            # Each community gets a minimum coherent example even at size=1.
            for n in range(max(1, round(len(members)*profile['sessions_per_person']))):
                sessions.append((scheduled(anchors), key, n))
            for n in range(max(1, round(len(members)*profile['posts_per_person']))):
                posts.append((scheduled(anchors), key, n))

    for at, key, n in sorted(sessions):
        group, channels, accounts = groups[key]
        channel = rng.choice([d for d in channels if 'member' in metadata(d)['writeRoles']])
        template_index = rng.randrange(len(kb['conversations']))
        template = kb['conversations'][template_index]
        turns = rng.randint(2, min(c.max_turns, len(template['turns'])+1))
        # Degree-like activity heterogeneity: early members are more active, but
        # all members remain eligible. Participants alternate where possible.
        participants = [rng.choices(accounts, weights=[1/(i+1) for i in range(len(accounts))])[0]]
        others = [a for a in accounts if a is not participants[0]]
        if others:
            participants.append(rng.choice(others))
        root, previous = None, None
        for turn in range(turns):
            author = participants[turn % len(participants)]
            step = {'act': 'opening', 'text': template['opening']} if turn == 0 else template['turns'][turn-1]
            doc = builder.add('message', f'chat-{key}-{n}-{turn}', community(group), at,
                              message=f'[SYNTHETIC] {template["topic"]} / session {n+1}: {step["text"]}',
                              platform=author['platform'], user=ref(author), group=group['id'], channel=channel['id'],
                              sentAt=at, isReply=turn > 0)
            root = root or doc
            doc['threadId'] = root['id']
            doc['messageId'] = doc['id']
            if previous:
                doc['replyTo'] = ref(previous)
                doc['mentions'] = [previous['user']] if previous['user'] != doc['user'] else []
            metadata(doc).update(socialKind='chat', groupId=group['id'], channelId=channel['id'],
                                 topic=template['topic'], templateIndex=template_index, sequence=turn,
                                 act=step['act'], session=n+1)
            previous = doc
            at += rng.randint(30, 180)

    for at, key, n in sorted(posts):
        group, channels, accounts = groups[key]
        channel = next(d for d in channels if metadata(d)['writeRoles'] == ['moderator'])
        moderator = accounts[0]
        template = rng.choice(kb['conversations'])
        topic = template['topic']
        root = builder.add('social-media-post', f'post-{key}-{n}', community(group), at,
                           content=f'[SYNTHETIC] {topic}: community update {n+1}. {template["opening"]}',
                           platform=moderator['platform'], userId=moderator['id'], authorRefs=[moderator['id']],
                           group=group['id'], channel=channel['id'], postedAt=iso(at), replyCount=0, repostCount=0)
        root['threadId'] = root['id']
        root['url'] = f'https://{moderator["platform"]}.example.invalid/posts/{root["id"].split(":")[1]}'
        metadata(root).update(socialKind='post', groupId=group['id'], channelId=channel['id'], topic=topic)
        for k, author in enumerate(rng.sample(accounts, min(2, len(accounts)))):
            at += rng.randint(60, 240)
            comment = builder.add('social-media-post', f'comment-{key}-{n}-{k}', community(group), at,
                                  content=f'[SYNTHETIC] Re: {topic}. {template["turns"][k]["text"]}',
                                  platform=author['platform'], userId=author['id'], authorRefs=[author['id']],
                                  group=group['id'], channel=channel['id'], postedAt=iso(at),
                                  parentPostId=root['id'], replyTo=root['id'], threadId=root['id'], isReply=True)
            metadata(comment).update(socialKind='comment', groupId=group['id'], channelId=channel['id'], topic=topic)
            root['replyCount'] += 1
        at += rng.randint(60, 240)
        author = rng.choice(accounts)
        channel = next(d for d in channels if 'member' in metadata(d)['writeRoles'])
        repost = builder.add('social-media-post', f'repost-{key}-{n}', community(group), at,
                             content=f'[SYNTHETIC] Sharing the {topic} community update for discussion.',
                             platform=author['platform'], userId=author['id'], authorRefs=[author['id']],
                             group=group['id'], channel=channel['id'], postedAt=iso(at), quotePostId=root['id'])
        repost['threadId'] = repost['id']
        metadata(repost).update(socialKind='repost', groupId=group['id'], channelId=channel['id'], topic=topic)
        root['repostCount'] = 1
        root['updatedAt'] = at  # Final engagement snapshot, no references to future records.


def social_references(doc):
    meta = metadata(doc)
    kind = meta.get('socialKind')
    if not kind:
        return
    for field in ('groupId', 'channelId'):
        if field in meta:
            yield {'id': meta[field], 'schema': 'org'}
    for channel in meta.get('channelIds', []):
        yield {'id': channel, 'schema': 'org'}
    if kind == 'chat':
        yield {'id': doc['threadId'], 'schema': 'message'}
    elif kind in ('post', 'comment', 'repost'):
        yield {'id': doc['userId'], 'schema': 'user'}
        for author in doc['authorRefs']:
            yield {'id': author, 'schema': 'user'}
        for field in ('parentPostId', 'replyTo', 'quotePostId', 'threadId'):
            if field in doc:
                yield {'id': doc[field], 'schema': 'social-media-post'}


def validate_social(documents, ids, kb):
    chats, comments, reposts, last_engagement = {}, Counter(), Counter(), {}
    for doc in documents:
        meta = metadata(doc)
        kind = meta.get('socialKind')
        if kind == 'account':
            group = ids[meta['groupId']]
            if metadata(group)['platform'] != doc['platform'] or meta['role'] not in ('member', 'moderator') or meta['joinedAt'] != doc['createdAt']:
                raise ValueError('invalid social membership')
            if any(metadata(ids[c])['groupId'] != group['id'] for c in meta['channelIds']):
                raise ValueError('channel membership outside group')
        if kind not in ('chat', 'post', 'comment', 'repost'):
            continue
        author = ids[doc['user']['id'] if kind == 'chat' else doc['userId']]
        group, channel = ids[meta['groupId']], ids[meta['channelId']]
        member = metadata(author)
        if member.get('socialKind') != 'account' or member['groupId'] != group['id'] or channel['id'] not in member['channelIds'] or member['joinedAt'] > doc['createdAt']:
            raise ValueError('author not a member at publication time')
        if metadata(channel)['groupId'] != group['id'] or doc['group'] != group['id'] or doc['channel'] != channel['id']:
            raise ValueError('social group/channel mismatch')
        if not author['platform'] == doc['platform'] == metadata(group)['platform'] or community(author) != community(group):
            raise ValueError('social platform/community mismatch')
        if kind != 'comment' and member['role'] not in metadata(channel)['writeRoles']:
            raise ValueError('role cannot publish in channel')
        content = doc['message'] if kind == 'chat' else doc['content']
        if not content.startswith('[SYNTHETIC]') or meta['topic'] not in content:
            raise ValueError('social content lost topic or synthetic label')
        if kind == 'chat':
            chats.setdefault(doc['threadId'], []).append(doc)
            if doc['sentAt'] != doc['createdAt']:
                raise ValueError('chat timestamp mismatch')
            for mention in doc.get('mentions', []):
                mentioned = metadata(ids[mention['id']])
                if mentioned.get('groupId') != group['id'] or channel['id'] not in mentioned.get('channelIds', []):
                    raise ValueError('mention outside channel membership')
        else:
            published = int(datetime.fromisoformat(doc['postedAt'].replace('Z', '+00:00')).timestamp())
            if published != doc['createdAt'] or doc['authorRefs'] != [author['id']]:
                raise ValueError('post author/timestamp mismatch')
            target_key = 'parentPostId' if kind == 'comment' else 'quotePostId' if kind == 'repost' else None
            if target_key:
                target = ids[doc[target_key]]
                if metadata(target).get('socialKind') != 'post' or metadata(target)['topic'] != meta['topic'] or target['createdAt'] >= doc['createdAt'] or target['group'] != group['id']:
                    raise ValueError('invalid social reply/repost target')
                last_engagement[target['id']] = max(doc['createdAt'], last_engagement.get(target['id'], 0))
                if kind == 'comment':
                    if doc['replyTo'] != target['id'] or doc['threadId'] != target['id'] or doc['channel'] != target['channel'] or not doc['isReply']:
                        raise ValueError('comment thread mismatch')
                    comments[target['id']] += 1
                else:
                    reposts[target['id']] += 1
    for root_id, history in chats.items():
        history.sort(key=lambda d: d['createdAt'])
        root = ids[root_id]
        for i, doc in enumerate(history):
            meta = metadata(doc)
            template = kb['social']['conversations'][meta['templateIndex']]
            step = {'act': 'opening', 'text': template['opening']} if i == 0 else template['turns'][i-1]
            expected = f'[SYNTHETIC] {template["topic"]} / session {meta["session"]}: {step["text"]}'
            if meta['templateIndex'] != metadata(root)['templateIndex'] or meta['session'] != metadata(root)['session'] or meta['sequence'] != i or meta['act'] != step['act'] or doc['message'] != expected or doc['channel'] != root['channel'] or meta['topic'] != metadata(root)['topic']:
                raise ValueError('conversation continuity mismatch')
            if i == 0:
                if doc is not root or doc['isReply'] or 'replyTo' in doc:
                    raise ValueError('invalid thread root')
            elif not doc['isReply'] or doc['replyTo']['id'] != history[i-1]['id'] or doc['createdAt'] <= history[i-1]['createdAt']:
                raise ValueError('invalid time-ordered reply chain')
            if i:
                previous = history[i-1]
                expected_mentions = [previous['user']] if previous['user'] != doc['user'] else []
                if doc['mentions'] != expected_mentions:
                    raise ValueError('reply mention does not match conversation partner')
    for doc in documents:
        if metadata(doc).get('socialKind') == 'post':
            if doc['replyCount'] != comments[doc['id']] or doc['repostCount'] != reposts[doc['id']]:
                raise ValueError('engagement count mismatch')
            if doc['updatedAt'] != last_engagement[doc['id']]:
                raise ValueError('engagement snapshot timestamp mismatch')
