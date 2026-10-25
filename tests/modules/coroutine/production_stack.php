<?php
$result=swr_context_markers();
if ($result['contexts']!==6 || $result['callbacks']!==0 || $result['checks']!==73) {
    throw new RuntimeException('Unexpected complete Context marker inventory: '.json_encode($result));
}
echo json_encode($result),"\n";
