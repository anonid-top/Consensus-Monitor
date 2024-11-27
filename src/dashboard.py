import re
import asyncio
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from src.calls import AioHttpCalls
from src.converter import pubkey_to_consensus_hex
from utils.logger import logger
from rich import box
from datetime import datetime, timezone, timedelta

class ConsensusDashboard:
    def __init__(self,
                 rpc: str,
                 refresh_per_second: int,
                 disable_emojis: bool,
                 refresh_validators: int,
                 refresh_consensus_state: int,
                 refresh_upgarde_plan: int,
                 refresh_node: int,
                 refresh_block_time: int,
                 user_tz: timedelta,
                 block_time_number: int,
                 columns: int,
                 hashes: bool
                 ):
        
        self.rpc = rpc
        self.rich_logger = None
        for handler in logger.handlers:
            if 'RichPanelLogHandler' in str(handler):
                self.rich_logger = handler
                break
        
        self.layout = Layout()
        self.console = Console()
        self.validators = []
        self.consensus_state = {}

        self.block_time = None
        self.node_height = None
        self.chain_id = None
        self.synced = False

        self.ugrade_name = None
        self.ugrade_height = None
        self.upgrade_time_left_seconds = None
        self.upgrade_time_unix = None

        self.online_validators = 0

        self.refresh_validators = refresh_validators
        self.refresh_consensus_state = refresh_consensus_state
        self.refresh_upgarde_plan = refresh_upgarde_plan
        self.refresh_per_second = refresh_per_second
        self.refresh_node = refresh_node
        self.refresh_block_time = refresh_block_time
        self.disable_emojis = disable_emojis
        self.hashes = hashes
        self.block_time_check_number = block_time_number
        self.columns = columns
        self.user_tz = user_tz


        self.layout.split_column(
            Layout(name="header", ratio=1),
            Layout(name="main", ratio=5),
            Layout(name="footer", ratio=1)
        )

        self.layout["header"].split_row(
            Layout(name="network_info", ratio=1),
            Layout(name="consensus_info", ratio=1),
            Layout(name="logs", ratio=1)
        )

        # self.layout["footer"].split_row(
            # Layout(name="votes_commits_step_bar"),
        # )

    async def update_node_status(self):
        try:
            async with AioHttpCalls(rpc=self.rpc) as session:
                rpc_status = await session.get_rpc_status()
            if rpc_status:
                self.synced = True if rpc_status.get('sync_info',{}).get('catching_up') is False else False
                self.chain_id = rpc_status.get('node_info',{}).get('network', 'N/A')
                self.node_height = int(rpc_status['sync_info']['latest_block_height']) if rpc_status.get('sync_info', {}).get('latest_block_height') else None
                logger.info(f"Updated node status | Height: {self.node_height}")
            else:
                logger.error(f"Failed to update node status")
        except Exception as e:
            logger.error(f"An error occurred while updating node status {e}")

    async def update_upgrade(self):
        try:
            async with AioHttpCalls(rpc=self.rpc) as session:
                ugrade_plan = await session.get_upgrade_info()
            if ugrade_plan:
                ugrade_plan = ugrade_plan.get('plan', {})
                if 'height' in ugrade_plan:
                    self.ugrade_height = int(ugrade_plan['height'])
                    self.ugrade_name = ugrade_plan.get('name', 'N/A')
                logger.info("Updated upgrade plan")
            else:
                logger.info("No upgrade detected")
                self.ugrade_height = None
                self.ugrade_name = None
        except Exception as e:
            logger.error(f"An error occurred while updating upgrade plan: {e}")

    def demojize(self, moniker):
        try:
            emoji_pattern = re.compile("[\U00010000-\U0010ffff]", flags=re.UNICODE)
            allowed_pattern = re.compile(r'[^a-zA-Z0-9_\-& ]')
            text_without_emojis = emoji_pattern.sub('', moniker)
            cleaned_text = allowed_pattern.sub('', text_without_emojis)
            return cleaned_text.strip()
        except Exception as e:
            logger.warning(f"An error occurred while demojizing validator's moniker {moniker}: {e}")
            return moniker

    async def update_validators(self):
        try:
            async with AioHttpCalls(rpc=self.rpc) as session:
                data = await session.get_validators(status='BOND_STATUS_BONDED')
                if not data:
                    logger.error("Failed to fetch validators. Will retry")
                    return
            
                if data:
                    sorted_vals = sorted(data, key=lambda x: int(x['tokens']), reverse=True)
                    validators = []
                    total_stake = sum(int(x['tokens']) for x in sorted_vals)
                    for validator  in sorted_vals:
                        _consensus_pub_key = validator.get('consensus_pubkey',{}).get('key')
                        if not _consensus_pub_key:
                            logger.warning(f'Skipping validator due too missing consensus_pub_key: {validator}')
                            continue
                        _moniker = self.demojize(validator.get('description',{}).get('moniker', 'N/A'))
                        _tokens = int(validator['tokens'])

                        _hex = pubkey_to_consensus_hex(pub_key=_consensus_pub_key)
                        validators.append({
                            'moniker': _moniker,
                            'hex': _hex,
                            'vp': round((_tokens / total_stake) * 100, 4)
                            })

                    self.validators = validators
                    logger.info(f"Updated validators | Current active set: {len(self.validators)}")

        except Exception as e:
            logger.error(f"An error occurred while updating validators {e}")

    def block_time_to_unix(self, time: str) -> float:
        time_str = time[:-4] + time[-1]
        timestamp = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        timestamp_utc = timestamp.replace(tzinfo=timezone.utc)
        return timestamp_utc.timestamp()

    async def update_block_time(self):
        try:
            async with AioHttpCalls(rpc=self.rpc) as session:
                tasks = []
                for i in range(self.block_time_check_number):
                    tasks.append(session.get_block(height=self.node_height-i))
                result = await asyncio.gather(*tasks)
            converted_blocks_timestamp = []
            for block in result:
                if block:
                    block_timestamp = self.block_time_to_unix(block['block']['header']['time'])
                    converted_blocks_timestamp.append(block_timestamp)
            if not converted_blocks_timestamp:
                logger.warning("Failed to update block time")
                return

            converted_blocks_timestamp.reverse()
            time_diffs = [converted_blocks_timestamp[i] - converted_blocks_timestamp[i - 1] for i in range(1, len(converted_blocks_timestamp))]

            self.block_time = sum(time_diffs) / len(time_diffs)

            logger.info(f"Updated block time:{self.block_time}")
        except Exception as e:
            logger.error(f"Failed to update block time: {e}")  
    
    def update_upgrade_time(self):
        try:
            logger.debug(f"Calculating estimated upgrade time")
            current_time_unix = int(datetime.now().replace(tzinfo=timezone.utc).timestamp())
            blocks_left = self.ugrade_height - self.node_height
            _time_left_seconds = int(blocks_left * self.block_time)
            self.upgrade_time_left_seconds = _time_left_seconds
            self.upgrade_time_unix = _time_left_seconds + current_time_unix
            logger.debug(f"Upgrade time UNIX: {self.upgrade_time_unix}")
        except Exception as e:
            logger.error(f"Failed to estimate upgrade time: {e}")  

    async def update_consensus_state(self):
        try:
            async with AioHttpCalls(rpc=self.rpc) as session:
                data = await session.get_consensus_state()                
            if not data:
                logger.error("Failed to fetch consensus_state. Will retry")
                return

            height_round_step = data['round_state']['height/round/step'].split('/')
            _height = int(height_round_step[0])
            _round = int(height_round_step[1])
            _step = int(height_round_step[2])

            self.consensus_state['round'] = _round
            self.consensus_state['height'] = _height
            self.consensus_state['step'] = _step
            self.consensus_state['hash'] = data['round_state']['proposal_block_hash']
            self.consensus_state['proposer_hex'] = data['round_state']['proposer']['address']

            consensus = data['round_state']['height_vote_set'][_round]

            _prevote_array = float(consensus['prevotes_bit_array'].split('=')[-1].strip()) * 100
            _precommits_array = float(consensus['precommits_bit_array'].split('=')[-1].strip()) * 100
            self.consensus_state['prevote_array'] = _prevote_array
            self.consensus_state['precommits_array'] = _precommits_array

            _online_precommit = 0
            _precommits_hex = {}
            for precommit in consensus['precommits']:
                if 'SIGNED_MSG_TYPE_PRECOMMIT(Precommit)' in precommit:
                    _online_precommit += 1
                    commit = precommit.split()[2]
                    hex = precommit.split()[0][-12:]
                    _precommits_hex[hex] = commit
                else:
                    continue
            self.consensus_state['hex_precommit'] = _precommits_hex
            
            _online_prevote = 0
            _prevotes_hex = {}
            for prevote in consensus['prevotes']:
                if 'SIGNED_MSG_TYPE_PREVOTE(Prevote)' in prevote:
                    _online_prevote += 1
                    vote = prevote.split()[2]
                    hex = prevote.split()[0][-12:]
                    _prevotes_hex[hex] = vote
                else:
                    continue
            self.consensus_state['hex_prevote'] = _prevotes_hex
            self.online_validators = _online_prevote if _online_prevote > _online_precommit else _online_precommit
            self.prevoting_validators = _online_prevote
            self.precommitting_validators = _online_precommit
            logger.info(f"Updated consensus state | {data['round_state']['height/round/step']}")

        except Exception as e:
            logger.error(f"An unexpected error occurred while processing consensus_state {e}")
            return
        
    def create_bar(self, label: str, value: float) -> str:
        bar_length = 60
        filled_length = int(value * bar_length // 100)
        if self.disable_emojis:
            bar = 'X' * filled_length + '-' * (bar_length - filled_length)
        else:
            bar = '█' * filled_length + '□' * (bar_length - filled_length)
        return f"[bold cyan]{label}[/bold cyan] {bar} {value:.1f}%"

    def create_step_bar(self, label: str, value: float, _max: float = 6) -> str:
        value = max(0, min(value, _max))
        bar_length = 60
        filled_length = int(value * bar_length // _max)
        if self.disable_emojis:
            bar = 'X' * filled_length + '-' * (bar_length - filled_length)
        else:
            bar = '█' * filled_length + '□' * (bar_length - filled_length)
        return f"[bold cyan]{label}[/bold cyan] {bar} {value}/{_max}"

    def generate_table(self) -> Table:
        table = Table(show_lines=False, expand=True, box=None)
        table.add_column("", justify="left")
        table.add_column("", justify="left")
        table.add_column("", justify="left")

        column_data = [[] for _ in range(self.columns)]

        self.consensus_state['proposer_moniker'] = 'N/A'
        for index, validator in enumerate(self.validators):
            column_index = index % self.columns
            moniker = validator['moniker'][:15].ljust(18)
            _hex_short = validator['hex'][:12]
            _voting_power = validator['vp']

            if self.consensus_state['proposer_hex'] == validator['hex']:
                self.consensus_state['proposer_moniker'] = validator['moniker']

            _prevote = self.consensus_state['hex_prevote'].get(_hex_short)
            _precommit = self.consensus_state['hex_precommit'].get(_hex_short)
            _index_str = f"{index + 1}.".ljust(4)

            if self.hashes:
                _symbol = _prevote if _prevote else "[X]".ljust(12)
                _color = 'bold green' if _prevote else 'bold red'
                column_data[column_index].append(
                    f"{_index_str}{moniker}{_voting_power:.1f}%  [{_color}]{_symbol}[/{_color}]"
                )

            else:
                _positive_symbol = "[bold green][V][/bold green]" if self.disable_emojis else "✅"
                _negative_symbol = "[bold red][X][/bold red]" if self.disable_emojis else "❌"

                _first_symbol = _positive_symbol if _prevote else _negative_symbol
                _second_symbol = _positive_symbol if _precommit else _negative_symbol

                column_data[column_index].append(
                    f"{_index_str}{moniker}{_voting_power:.1f}%  {_first_symbol}{_second_symbol.ljust(10)}"
                )

        max_rows = max(len(col) for col in column_data)
        for row_index in range(max_rows):
            row = [
                column_data[col_index][row_index] if row_index < len(column_data[col_index]) else ""
                for col_index in range(self.columns)
            ]
            table.add_row(*row)

        return table

    async def start(self):
        try:
            
            with Live(self.layout, refresh_per_second=self.refresh_per_second, auto_refresh=False) as live:
                while True:
                    log_renderable = self.rich_logger.get_logs()
                    log_panel = Panel(log_renderable, expand=True, box=box.SIMPLE)
                    self.layout["header"]["logs"].update(log_panel)

                    if not hasattr(self, "_last_upgrade_update") or (asyncio.get_event_loop().time() - self._last_upgrade_update) >= self.refresh_upgarde_plan:
                        await self.update_upgrade()
                        self._last_upgrade_update = asyncio.get_event_loop().time()

                    if not hasattr(self, "_last_node_status_update") or (asyncio.get_event_loop().time() - self._last_node_status_update) >= self.refresh_node:
                        await self.update_node_status()
                        self._last_node_status_update = asyncio.get_event_loop().time()

                    if not hasattr(self, "_last_validators_update") or (asyncio.get_event_loop().time() - self._last_validators_update) >= self.refresh_validators:
                        await self.update_validators()
                        self._last_validators_update = asyncio.get_event_loop().time()

                    if not hasattr(self, "_last_consensus_update") or (asyncio.get_event_loop().time() - self._last_consensus_update) >= self.refresh_consensus_state:
                        await self.update_consensus_state()
                        self._last_consensus_update = asyncio.get_event_loop().time()

                    if not hasattr(self, "_last_block_time_update") or (asyncio.get_event_loop().time() - self._last_block_time_update) >= self.refresh_block_time:
                        await self.update_block_time()
                        self._last_block_time_update = asyncio.get_event_loop().time()


                    consensus_info = ""
                    if self.consensus_state and self.validators:
                        self.layout["main"].update(self.generate_table())
                        prevote_bar = self.create_bar("[ Prevotes ]", self.consensus_state['prevote_array'])
                        precommit_bar = self.create_bar("[Precommits]", self.consensus_state['precommits_array'])
                        step_bar = self.create_step_bar("[   Step   ]", self.consensus_state['round'])

                        votes_commits_renderable = f"{prevote_bar}\n{precommit_bar}\n{step_bar}"
                        votes_commits_panel = Panel(votes_commits_renderable, box=box.SIMPLE, expand=True)
                        self.layout["footer"].update(votes_commits_panel)

                        consensus_info += f"[bold cyan]Height/Round/Step:[/bold cyan] {self.consensus_state['height']}/{self.consensus_state['round']}/{self.consensus_state['step']}\n"
                        consensus_info += f"[bold cyan]Proposer:[/bold cyan] {self.consensus_state['proposer_moniker']}\n"
                        consensus_info += f"[bold cyan]Proposal Hash:[/bold cyan] {self.consensus_state['hash'] or 'N/A'}\n"
                        consensus_info += f"[bold cyan]Online validators:[/bold cyan] {self.online_validators} / {len(self.validators)}\n"
                        consensus_info += f"[bold cyan]Offline validators:[/bold cyan] {len(self.validators) - self.online_validators}\n"
                        consensus_info += f"[bold cyan]Prevoting validators:[/bold cyan] {self.prevoting_validators}\n"
                        consensus_info += f"[bold cyan]Precommitting validators:[/bold cyan] {self.precommitting_validators}\n"

                        # consensus_info += f"{prevote_bar}\n{precommit_bar}\n{step_bar}"
                        consensus_info_panel = Panel(consensus_info, title="Consensus Info", border_style="green", expand=True)
                        self.layout["header"]["consensus_info"].update(consensus_info_panel)

                    network_info = ""
                    network_info += f"[bold cyan]Node Online & Synced:[/bold cyan] {self.synced} | {self.node_height}\n"
                    network_info += f"[bold cyan]Chain ID:[/bold cyan] {self.chain_id}\n"
                    if self.block_time:
                        network_info += f"[bold cyan]Block time[/bold cyan] {str(self.block_time):.4}\n"

                    if self.ugrade_height and self.node_height:
                        self.update_upgrade_time()
                        blocks_left = self.ugrade_height - self.node_height
                        network_info += f"[bold cyan]Upgrade:[/bold cyan] {self.ugrade_name} | Height: {self.ugrade_height} | Blocks left: {blocks_left}"
                        if self.upgrade_time_unix:
                            time = datetime.fromtimestamp(self.upgrade_time_unix, timezone.utc)
                            time_in_user_tz = time.astimezone(self.user_tz).strftime('%Y-%m-%d %H:%M:%S')
                            network_info += f" | Time: {time_in_user_tz}"

                            if self.upgrade_time_left_seconds:
                                if self.upgrade_time_left_seconds > 0:
                                    hours, remainder = divmod(self.upgrade_time_left_seconds, 3600)
                                    minutes, seconds = divmod(remainder, 60)
                                    human_readable_countdown = f"in {hours} hours {minutes} minutes {seconds} seconds"
                                    network_info += f" ({human_readable_countdown})"
                                else:
                                    network_info += " (already occurred)"

                    network_info_panel = Panel(network_info, title="Network Info", border_style="blue_violet", expand=True)
                    self.layout["header"]["network_info"].update(network_info_panel)

                    live.refresh()
                    await asyncio.sleep(1 / self.refresh_per_second)

        finally:
            self.console.clear()

